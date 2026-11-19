#!/usr/bin/env python3
"""Build and verify FormEditor artifacts with the Linux 1C platform in Docker."""

import argparse
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile


MD = "http://v8.1c.ru/8.3/MDClasses"
_REPORT_SPEC = importlib.util.spec_from_file_location("test_report", Path(__file__).with_name("test_report.py"))
test_report = importlib.util.module_from_spec(_REPORT_SPEC)
_REPORT_SPEC.loader.exec_module(test_report)
EXPECTED_RUNTIME_IDS = {item["id"] for item in test_report.load_manifest()["scenarios"]}
REQUIRED_CHECKS = {
    "container-preflight", "python-unit-tests", "edt-compilation",
    "build-and-verify-cf-cfe", "install-and-verify-cfe", "designer-syntax",
    "ui-cf", "runtime-cf", "runtime-cfe",
}


def normalized_module(path):
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")
    return text.replace("\r\n", "\n")


def validate_ui_report(report):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("UI test report has an unsupported schema")
    if report.get("suite") != "FormEditor UI" or report.get("status") not in {"PASS", "FAIL"}:
        raise ValueError("UI test report has an invalid suite or status")
    records = report.get("results")
    if not isinstance(records, list) or not records:
        raise ValueError("UI test report has no scenario results")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("UI test report contains a non-object scenario record")
    ui_manifest = json.loads((Path(__file__).resolve().parents[1] / "tests" / "ui-scenarios.json").read_text(encoding="utf-8"))
    expected_ids = [item["id"] for item in ui_manifest["scenarios"]]
    if [record.get("id") for record in records] != expected_ids:
        raise ValueError("UI test report IDs do not match the required UI scenarios")
    for record in records:
        if (not isinstance(record.get("description"), str) or not record["description"].strip()
                or record.get("status") not in {"PASS", "FAIL"}
                or not isinstance(record.get("expected"), str)
                or not isinstance(record.get("actual"), str)
                or not isinstance(record.get("error"), str)):
            raise ValueError("UI test report contains an incomplete scenario record")
        screenshot = record.get("screenshot")
        if screenshot is not None and screenshot != f"screenshots/{record['id']}.png":
            raise ValueError(f"UI screenshot path is not allowed for {record['id']}")
        screenshot_error = record.get("screenshot_error")
        if screenshot_error is not None and not isinstance(screenshot_error, str):
            raise ValueError(f"UI screenshot error is invalid for {record['id']}")
    passed = sum(record["status"] == "PASS" for record in records)
    failed = len(records) - passed
    totals = {"total": len(records), "passed": passed, "failed": failed}
    if report.get("totals") != totals:
        raise ValueError("UI test report totals do not match its records")
    expected_status = "PASS" if failed == 0 else "FAIL"
    if report["status"] != expected_status:
        raise ValueError("UI test report status does not match its records")
    return report


def ui_method_coverage(records, project, block_reason=None):
    """Match every exported common-module method to a required UI scenario or a support exclusion."""
    project = Path(project)
    ui_manifest = json.loads((Path(__file__).resolve().parents[1] / "tests" / "ui-scenarios.json").read_text(encoding="utf-8"))
    coverage_path = Path(__file__).resolve().parents[1] / "tests" / "ui-method-coverage.json"
    coverage_manifest = json.loads(coverage_path.read_text(encoding="utf-8"))
    if coverage_manifest.get("schema_version") != 1:
        raise ValueError("Unsupported UI method coverage schema")
    methods = coverage_manifest.get("methods")
    if not isinstance(methods, list) or not methods:
        raise ValueError("UI method coverage must contain methods")
    names = [item.get("method") for item in methods]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("UI method coverage contains invalid or duplicate method names")
    module_path = project / "FormEditor/src/CommonModules/РедакторФорм/Module.bsl"
    module_text = normalized_module(module_path)
    exported = re.findall(r"(?m)^\s*(?:Функция|Процедура)\s+([^\s(]+)\s*\([^\n]*\)\s+Экспорт\s*$", module_text)
    if set(exported) != set(names):
        missing = sorted(set(exported) - set(names))
        stale = sorted(set(names) - set(exported))
        raise ValueError(f"UI method inventory differs from module exports; missing={missing}; stale={stale}")
    known_scenarios = {item["id"] for item in ui_manifest["scenarios"]}
    if any(item.get("required") and item.get("scenario") not in known_scenarios for item in methods):
        raise ValueError("A required UI method has no scenario in tests/ui-scenarios.json")
    by_id = {item["id"]: item for item in records or []}
    rows = []
    for item in methods:
        scenario_id = item.get("scenario")
        record = by_id.get(scenario_id)
        if not item.get("required"):
            status, observed = "NOT_APPLICABLE", "helper; no user-interface element"
        elif record is not None:
            status = record["status"]
            observed = record.get("actual") or record.get("error") or ""
        elif block_reason:
            status, observed = "BLOCKED", str(block_reason)
        else:
            status, observed = "NOT_TESTED", "scenario record missing"
        rows.append({"method": item["method"], "scope": item["scope"],
                     "required": item["required"], "scenario": scenario_id,
                     "relationship": item["relationship"], "status": status,
                     "observed": observed})
    return rows


def runtime_result(path, known_failures=None):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError("1C did not produce the runtime test report")
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        test_report.validate_result(report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"1C runtime report is missing or invalid: {error}") from error

    if report["status"] == "BLOCKED":
        return {
            "suite_status": "BLOCKED",
            "block_reason": report["block_reason"],
            "total": 0,
            "passed": 0,
            "failed": 0,
            "known_failures": [],
            "new_failures": [],
            "resolved_baseline_failures": [],
            "results": [],
        }

    known_failures = known_failures or {}
    known = []
    new = []
    resolved = []
    for record in report["results"]:
        name = record["id"]
        baseline = known_failures.get(name)
        if record["status"] == "PASS":
            if baseline:
                resolved.append(name)
            continue
        error_text = " ".join(str(record.get(field) or "")
                              for field in ("description", "expected", "actual", "error"))
        signature = baseline["signature"] if baseline else ""
        # Baseline entries use the human-readable wording from the prior text
        # report. Match that assertion phrase in the structured error payload.
        if "не пройдено условие «" in signature:
            signature = signature.split("не пройдено условие «", 1)[1].split("»", 1)[0]
        if baseline and signature and signature in error_text:
            known.append(name)
        else:
            new.append({"id": name, "detail": record.get("error") or record.get("actual") or record["description"]})

    return {
        "suite_status": report["status"],
        "total": report["totals"]["total"],
        "passed": report["totals"]["passed"],
        "failed": report["totals"]["failed"],
        "known_failures": sorted(known),
        "new_failures": new,
        "resolved_baseline_failures": sorted(resolved),
        "results": report["results"],
    }


def runtime_process_outcome(return_code, report, detail=""):
    """Accept only a complete report from a cleanly exited client process."""
    if return_code != 0:
        return {"status": "BLOCKED", "block_reason": detail or f"1C client exited with code {return_code}",
                "diagnostic_report": report}
    if report is None:
        return {"status": "BLOCKED", "block_reason": detail or "1C client produced no structured report",
                "diagnostic_report": None}
    return {"status": "RESULT", "report": report}


class OrchestrationBlocked(RuntimeError):
    """The test process could not produce an authoritative scenario result."""


def load_runtime_baseline(path, platform_version, architecture):
    if not path.is_file():
        return {"id": None, "known_failures": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"Unsupported runtime baseline schema in {path}")
    entry = data.get("platforms", {}).get(platform_version, {}).get(architecture)
    if not entry:
        return {"id": None, "known_failures": {}}
    known_failures = entry.get("known_failures", {})
    expected = EXPECTED_RUNTIME_IDS
    unknown = set(known_failures) - expected
    if unknown:
        raise ValueError("Baseline contains unknown runtime IDs: " + ", ".join(sorted(unknown)))
    for name, failure in known_failures.items():
        if not isinstance(failure, dict) or not failure.get("signature") or not failure.get("issue"):
            raise ValueError(f"Baseline entry for {name} must include issue and failure signature")
    return {
        "id": f"{platform_version}/{architecture}",
        "source": entry.get("source", ""),
        "known_failures": known_failures,
    }


def load_edt_baseline(path):
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"Unsupported EDT baseline schema in {path}")
    findings = data.get("edt_known_significant", [])
    for finding in findings:
        if not all(finding.get(key) for key in ("rule", "object", "message")):
            raise ValueError("EDT baseline entries must include rule, object and message")
    return findings


def validate_edt_report(path, known_significant=None):
    known_significant = known_significant or []
    if not path.is_file():
        raise RuntimeError("EDT did not produce a validation report")
    counts = {}
    errors = []
    current_significant = []
    malformed = []
    rows = 0
    severities = {"Ошибка конфигурации", "Значительная", "Незначительная", "Тривиальная"}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        columns = line.split("\t")
        if len(columns) < 8:
            malformed.append(line)
            continue
        severity = columns[1]
        rows += 1
        if severity not in severities:
            malformed.append(line)
            continue
        counts[severity] = counts.get(severity, 0) + 1
        finding = {"rule": columns[4], "object": columns[5], "message": columns[7]}
        if severity == "Ошибка конфигурации":
            errors.append(finding)
        elif severity == "Значительная":
            current_significant.append(finding)

    def same_finding(left, right):
        return all(left[key] == right[key] for key in ("rule", "object", "message"))

    accepted = [finding for finding in current_significant
                if any(same_finding(finding, known) for known in known_significant)]
    new_significant = [finding for finding in current_significant
                       if not any(same_finding(finding, known) for known in known_significant)]
    if rows == 0 or malformed or errors or new_significant:
        problems = []
        if rows == 0:
            problems.append("empty report")
        if malformed:
            problems.append(f"malformed EDT rows: {len(malformed)}")
        if errors:
            problems.append(f"configuration errors: {len(errors)}")
        if new_significant:
            problems.append(f"new significant findings: {len(new_significant)}")
        raise RuntimeError("EDT validation failed: " + "; ".join(problems))
    resolved = [finding for finding in known_significant
                if not any(same_finding(finding, current) for current in current_significant)]
    return {
        "severity_counts": counts,
        "accepted_significant": accepted,
        "resolved_significant": resolved,
        "new_significant": [],
    }


def release_decision(checks, built, extension_verified, allow_known_baseline_failures,
                     source_state="clean"):
    statuses = {item["status"] for item in checks}
    allowed_check_statuses = {"passed", "baseline-only", "failed", "blocked"}
    if not built or not extension_verified:
        return {"status": "build-failed", "release_allowed": False, "exit_code": 5}
    names = [item.get("name") for item in checks]
    if set(names) != REQUIRED_CHECKS or len(names) != len(REQUIRED_CHECKS):
        return {"status": "candidate", "release_allowed": False, "exit_code": 1}
    if any(item["status"] == "baseline-only" and item["name"] not in {"runtime-cf", "runtime-cfe"}
           for item in checks):
        return {"status": "candidate", "release_allowed": False, "exit_code": 1}
    if not statuses.issubset(allowed_check_statuses):
        return {"status": "candidate", "release_allowed": False, "exit_code": 1}
    if "blocked" in statuses:
        return {"status": "blocked", "release_allowed": False, "exit_code": 3}
    if "failed" in statuses:
        return {"status": "candidate", "release_allowed": False, "exit_code": 1}
    if source_state != "clean":
        status = "source_dirty" if source_state == "dirty" else "source_unknown"
        return {"status": status, "release_allowed": False, "exit_code": 4}
    if "baseline-only" in statuses:
        if allow_known_baseline_failures:
            return {"status": "verified_with_baseline", "release_allowed": True, "exit_code": 0}
        return {"status": "baseline_only", "release_allowed": False, "exit_code": 2}
    return {"status": "verified", "release_allowed": True, "exit_code": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--platform-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edt-report", type=Path, required=True)
    parser.add_argument("--allow-known-baseline-failures", action="store_true",
                        help="permit release with only explicitly recorded baseline failures")
    parser.add_argument("--source-revision", default="unknown")
    parser.add_argument("--source-state", choices=("clean", "dirty", "unknown"), default="unknown")
    parser.add_argument("--test-only", action="store_true",
                        help="run the same CF/CFE checks and reports without release packaging or source-clean policy")
    parser.add_argument("--retain-bases", action="store_true",
                        help="keep CF/CFE infobases in output/test-bases for manual review")
    parser.add_argument("--manual", action="store_true",
                        help="retain test bases and open both managed forms on the container's active display")
    args = parser.parse_args()
    if args.manual:
        args.test_only = True
        args.retain_bases = True
    source, project, platform, output = [p.resolve() for p in (
        args.export, args.project, args.platform_bin, args.output)]
    architecture = platform.parent.name
    baseline_path = project / "tests" / "release-baseline.json"
    baseline = load_runtime_baseline(baseline_path, platform.name, architecture)
    edt_baseline = load_edt_baseline(baseline_path)
    output.mkdir(parents=True, exist_ok=False)
    reports = output / "reports"
    reports.mkdir()
    checks = []
    ui_state = {}
    ui_state["scenarios"] = json.loads((project / "tests" / "ui-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    ui_state["coverage"] = ui_method_coverage([], project, "UI stage has not run")
    checks.append({"name": "container-preflight", "status": "passed",
                   "detail": "Release test process started inside the configured container"})
    started = time.time()
    environment = os.environ.copy()
    environment["PATH"] = str(platform) + os.pathsep + environment.get("PATH", "")
    # 1C's bundled libstdc++ predates Ubuntu's current WebKit build.
    for library in (Path("/usr/lib/aarch64-linux-gnu/libstdc++.so.6"),
                    Path("/usr/lib/x86_64-linux-gnu/libstdc++.so.6")):
        if library.is_file():
            environment["LD_PRELOAD"] = str(library)
            break

    def run(label, command, timeout=180, gui=False, allow_nonzero=False):
        log = reports / (label + ".log")
        print(label, flush=True)
        command_environment = environment
        command = [str(part) for part in command]
        if gui:
            command_environment = environment.copy()
            xvfb_log = reports / (label + "-xvfb.log")
            server_args = "-screen 0 1280x1024x24 -nolisten tcp -ac"
            command = ["xvfb-run", "--auto-servernum", f"--server-args={server_args}",
                       f"--error-file={xvfb_log}", *command]
        with log.open("w") as stream:
            try:
                process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                           env=command_environment, start_new_session=True)
            except OSError as error:
                raise OrchestrationBlocked(f"Could not start {label}: {error}") from error
            try:
                result = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise OrchestrationBlocked(f"{label} timed out after {timeout}s") from error
        if result and not allow_nonzero:
            details = log.read_text(encoding="utf-8-sig", errors="replace").strip()[-2000:]
            raise RuntimeError(f"{label} exited with code {result}; see {log}\n{details}")
        return result

    def ib(label, *arguments):
        run(label, [platform / "ibcmd", *arguments])

    def check(label, operation):
        try:
            result = operation()
        except Exception as error:
            blocked = isinstance(error, OrchestrationBlocked) or "лицензи" in str(error).lower() or "license" in str(error).lower()
            status = "blocked" if blocked else "failed"
            check_result = {"name": label, "status": status, "detail": str(error)}
            if label == "ui-cf" and ui_state.get("scenarios"):
                check_result.update({
                    "suite_status": "BLOCKED",
                    "block_reason": str(error),
                    "method_coverage": ui_method_coverage([], project, str(error)),
                    "ui_scenarios": [
                        {"id": item["id"], "status": "BLOCKED", "description": item["description"],
                         "expected": "TestClient interaction completed", "actual": "",
                         "error": str(error)}
                        for item in ui_state["scenarios"]
                    ],
                })
            checks.append(check_result)
            print(f"{status.upper()} {label}: {error}", flush=True)
            return False
        if isinstance(result, dict) and result.get("suite_status") == "BLOCKED":
            checks.append({"name": label, "status": "blocked", **result})
            print(f"BLOCKED {label}: {result.get('block_reason', 'no runtime result')}", flush=True)
            return False
        if isinstance(result, dict) and "new_failures" in result:
            if result["new_failures"]:
                status = "failed"
                checks.append({"name": label, "status": status, **result})
                print(f"FAILED {label}: new runtime failures: " + ", ".join(
                    item["id"] for item in result["new_failures"]), flush=True)
                return False
            if result["known_failures"]:
                status = "baseline-only"
                checks.append({"name": label, "status": status, **result})
                print(f"BASELINE {label}: " + ", ".join(result["known_failures"]), flush=True)
                return True
            if result.get("suite_status") == "FAIL":
                checks.append({"name": label, "status": "failed", **result})
                print(f"FAILED {label}: suite reported FAIL without baseline classification", flush=True)
                return False
            checks.append({"name": label, "status": "passed", **result})
            return True
        if isinstance(result, dict):
            checks.append({"name": label, "status": "passed", **result})
        else:
            checks.append({"name": label, "status": "passed"})
        return True

    check("python-unit-tests", lambda: run(
        "python-unit-tests", [sys.executable, "-m", "unittest", "discover",
                              "-s", project / "tests", "-v"], timeout=300))

    version = ET.parse(source / "Configuration.xml").findtext(
        f"{{{MD}}}Configuration/{{{MD}}}Properties/{{{MD}}}Version")
    if not version:
        raise ValueError("Configuration version is missing")
    module_relative = Path("CommonModules/РедакторФорм/Ext/Module.bsl")
    original_module = project / "FormEditor/src/CommonModules/РедакторФорм/Module.bsl"
    modules = {}
    for module in (project / "FormEditor/src").rglob("*.bsl"):
        parts = module.relative_to(project / "FormEditor/src").parts
        if parts[0] == "Configuration":
            exported = Path("Ext") / parts[-1]
        elif parts[0] == "CommonModules":
            exported = Path(*parts[:-1]) / "Ext" / parts[-1]
        elif len(parts) == 5 and parts[0] == "DataProcessors" and parts[2] == "Forms":
            exported = Path(*parts[:-1]) / "Ext/Form" / parts[-1]
        else:
            raise ValueError(f"Unknown module export path: {module}")
        if normalized_module(module) != normalized_module(source / exported):
            raise ValueError(f"Stale EDT export: {module}")
        modules[exported] = module

    spec = importlib.util.spec_from_file_location("prepare_extension", Path(__file__).with_name("prepare-extension.py"))
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    if args.edt_report:
        def validate_edt():
            shutil.copyfile(args.edt_report, reports / "edt-validation.tsv")
            return validate_edt_report(args.edt_report, edt_baseline)
        check("edt-compilation", validate_edt)
    if args.retain_bases:
        work = output / "test-bases"
        work.mkdir()
        work_context = nullcontext(str(work))
    else:
        work_context = tempfile.TemporaryDirectory(prefix="formeditor-release-")
    with work_context as temporary:
        work = Path(temporary)
        database = work / "main-ib"
        extension_xml = work / "extension-xml"
        prepare.prepare(source, extension_xml)

        def build():
            ib("create-build-infobase", "infobase", "create", f"--db-path={database}")
            ib("build-cf", "config", "import", f"--db-path={database}", f"--out={output / 'FormEditor.cf'}", source)
            extension_db = work / "extension-build-ib"
            ib("create-cfe-infobase", "infobase", "create", f"--db-path={extension_db}")
            ib("create-build-extension", "config", "extension", "create", f"--db-path={extension_db}",
               "--name=FormEditor", "--name-prefix=рф_", "--purpose=add-on")
            ib("import-cfe", "config", "import", f"--db-path={extension_db}", "--extension=FormEditor", extension_xml)
            ib("build-cfe", "config", "save", f"--db-path={extension_db}", "--extension=FormEditor", output / "FormEditor.cfe")
            for artifact in (output / "FormEditor.cf", output / "FormEditor.cfe"):
                if not artifact.is_file() or artifact.stat().st_size < 1024:
                    raise RuntimeError(f"Missing or empty artifact: {artifact}")
            ib("load-cf", "config", "load", f"--db-path={database}", output / "FormEditor.cf")
            ib("check-cf", "config", "check", f"--db-path={database}")
            ib("apply-cf", "config", "apply", f"--db-path={database}", "--force")
            ib("roundtrip-cf", "config", "export", f"--db-path={database}", work / "roundtrip-cf")
            if normalized_module(work / "roundtrip-cf" / module_relative) != normalized_module(original_module):
                raise RuntimeError("CF roundtrip changed the common module")
            for exported, module in modules.items():
                if normalized_module(work / "roundtrip-cf" / exported) != normalized_module(module):
                    raise RuntimeError(f"CF roundtrip changed {module}")

        built = check("build-and-verify-cf-cfe", build)
        host = work / "extension-ib"

        def verify_extension():
            host_xml = work / "host-xml"
            shutil.copytree(source, host_xml)
            # A native extension extends the host module; keep it available so
            # the host form modules can resolve their common-module calls.
            ib("create-extension-host", "infobase", "create", f"--db-path={host}", f"--import={host_xml}", "--apply", "--force")
            ib("create-extension", "config", "extension", "create", f"--db-path={host}", "--name=FormEditor", "--name-prefix=рф_", "--purpose=add-on")
            ib("load-cfe", "config", "load", f"--db-path={host}", "--extension=FormEditor", output / "FormEditor.cfe")
            ib("check-cfe", "config", "check", f"--db-path={host}", "--extension=FormEditor")
            ib("apply-cfe", "config", "apply", f"--db-path={host}", "--extension=FormEditor", "--force")
            ib("roundtrip-cfe", "config", "export", f"--db-path={host}", "--extension=FormEditor", work / "roundtrip-cfe")
            if normalized_module(work / "roundtrip-cfe" / module_relative) != normalized_module(original_module):
                raise RuntimeError("CFE roundtrip changed the common module")

        extension_verified = check("install-and-verify-cfe", verify_extension) if built else False

        def syntax():
            log = reports / "syntax.txt"
            try:
                run("designer-syntax", [platform / "1cv8", "DESIGNER",
                    "/F" + str(database), "/CheckConfig", "-Server", "-ThinClient", "-WebClient",
                    "-ExternalConnection", "/DisableStartupDialogs", "/DisableStartupMessages", "/Out", log],
                    timeout=90, gui=True)
            except RuntimeError:
                if log.exists():
                    raise RuntimeError(log.read_text(encoding="utf-8-sig", errors="replace"))
                raise
            if not log.exists():
                raise RuntimeError("Designer did not produce its syntax report")
            text = log.read_text(encoding="utf-8-sig", errors="replace").strip()
            if text and text != "Ошибок не обнаружено":
                raise RuntimeError("Designer diagnostics: " + text)

        if built:
            check("designer-syntax", syntax)

        def ui_test(database_path):
            ui_state["scenarios"] = json.loads((project / "tests" / "ui-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
            ui_report_path = reports / "ui-cf" / "results.json"
            ui_report_path.parent.mkdir(parents=True, exist_ok=True)
            screenshots_dir = ui_report_path.parent / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            for path in (ui_report_path, Path(str(ui_report_path) + ".error.txt")):
                path.unlink(missing_ok=True)
            for path in screenshots_dir.iterdir():
                if path.is_file():
                    path.unlink()
            client_log = reports / "ui-cf-client.log"
            client_platform_report = reports / "ui-cf-client-platform.txt"
            for path in (client_log, client_platform_report):
                path.unlink(missing_ok=True)
            manager_log = reports / "ui-cf-manager.log"
            platform_report = reports / "ui-cf-platform.txt"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_probe:
                port_probe.bind(("127.0.0.1", 0))
                test_port = port_probe.getsockname()[1]
            client_args = [platform / "1cv8", "ENTERPRISE", "/F" + str(database_path),
                           "/TESTCLIENT", f"-TPort{test_port}",
                           "/DisableStartupDialogs", "/DisableStartupMessages",
                           "/Out", client_platform_report]
            manager_args = [platform / "1cv8", "ENTERPRISE", "/F" + str(database_path),
                            "/TESTMANAGER"]
            manager_parameter_prefix = ("/CFormEditorUITest=" +
                f"{test_port}|{ui_report_path}|{screenshots_dir}|{Path(__file__).resolve().with_name('capture_ui_failure.py')}|")
            manager_suffix = ["/DisableStartupDialogs", "/DisableStartupMessages", "/Out", platform_report]
            listener_probe = """\
import socket
import sys
import time

port = int(sys.argv[1])
deadline = time.monotonic() + 40
while time.monotonic() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            sys.exit(0)
    except OSError:
        time.sleep(0.2)
sys.exit(1)
"""
            shell_command = (
                f"{' '.join(shlex.quote(str(arg)) for arg in client_args)} "
                f">{shlex.quote(str(client_log))} 2>&1 & client_pid=$!; "
                f"python3 -c {shlex.quote(listener_probe)} {test_port}; readiness_rc=$?; "
                "if [[ \"$readiness_rc\" -ne 0 ]]; then "
                f"echo 'TestClient did not open its dedicated TCP listener on port {test_port}' >>{shlex.quote(str(client_log))}; "
                f"cat {shlex.quote(str(client_platform_report))} >>{shlex.quote(str(client_log))} 2>/dev/null || true; "
                "kill \"$client_pid\" 2>/dev/null || true; wait \"$client_pid\" 2>/dev/null || true; exit 3; fi; "
                f"{' '.join(shlex.quote(str(arg)) for arg in manager_args)} "
                f"{shlex.quote(manager_parameter_prefix)}\"$client_pid\" "
                f"{' '.join(shlex.quote(str(arg)) for arg in manager_suffix)} "
                f">{shlex.quote(str(manager_log))} 2>&1; manager_rc=$?; "
                "kill \"$client_pid\" 2>/dev/null || true; "
                "wait \"$client_pid\" 2>/dev/null || true; exit \"$manager_rc\"")
            try:
                return_code = run("ui-cf", ["bash", "-c", shell_command],
                                  timeout=180, gui=True, allow_nonzero=True)
            except OrchestrationBlocked:
                raise
            if return_code:
                detail = (manager_log.read_text(encoding="utf-8-sig", errors="replace").strip()[-3000:]
                          if manager_log.is_file() else "manager log was not created")
                raise OrchestrationBlocked(
                    f"Native TestManager exited with code {return_code}; see {manager_log}; {detail}")
            if not ui_report_path.is_file():
                diagnostic = Path(str(ui_report_path) + ".error.txt")
                details = diagnostic.read_text(encoding="utf-8-sig", errors="replace").strip()[-3000:] if diagnostic.is_file() else ""
                raise OrchestrationBlocked(
                    f"Native TestManager produced no UI report; see {manager_log}; {details}")
            try:
                ui_report = validate_ui_report(json.loads(ui_report_path.read_text(encoding="utf-8-sig")))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise OrchestrationBlocked(f"Native TestManager UI report is invalid: {error}") from error
            records = ui_report["results"]
            for record in records:
                if record.get("screenshot"):
                    record["screenshot"] = "../ui-cf/" + record["screenshot"]
            failed = [record for record in records if record["status"] == "FAIL"]
            coverage = ui_method_coverage(records, project)
            ui_state["coverage"] = coverage
            uncovered = [item for item in coverage if item["required"] and item["status"] != "PASS"]
            coverage_failures = [{"id": "coverage:" + item["method"],
                                  "detail": f"{item['status']} via {item['scenario']}: {item['observed']}"}
                                 for item in uncovered]
            first = records[0] if records else {"id": "none", "expected": "", "actual": ""}
            suite_status = "FAIL" if failed or uncovered else ui_report["status"]
            return {
                "suite_status": suite_status,
                "new_failures": failed + coverage_failures,
                "known_failures": [],
                "total": ui_report["totals"]["total"],
                "passed": ui_report["totals"]["passed"],
                "ui_results": records,
                "ui_scenarios": records,
                "method_coverage": coverage,
                "coverage_total": sum(item["required"] for item in coverage),
                "coverage_passed": sum(item["required"] and item["status"] == "PASS" for item in coverage),
                "detail": (f"{suite_status} {ui_report['totals']['passed']}/{ui_report['totals']['total']} scenarios; "
                           f"method coverage {sum(item['required'] and item['status'] == 'PASS' for item in coverage)}/"
                           f"{sum(item['required'] for item in coverage)}; report={ui_report_path}"),
            }

        if built:
            check("ui-cf", lambda: ui_test(database))

        def runtime(db, label):
            result = reports / (label + ".json")
            diagnostic_sidecar = Path(str(result) + ".error.txt")
            platform_report = reports / (label + "-platform.txt")

            def diagnostic_text():
                for path in (diagnostic_sidecar, platform_report, reports / (label + ".log"),
                             reports / (label + "-xvfb.log")):
                    if path.is_file():
                        detail = path.read_text(encoding="utf-8-sig", errors="replace").strip()
                        if detail:
                            return detail[-8000:]
                return ""

            def blocked(reason, diagnostic_report=None):
                report = test_report.blocked_report(
                    reason, args.source_revision, args.source_state)
                output_dir = reports / label
                test_report.write_reports(report, output_dir)
                if diagnostic_report is not None:
                    (output_dir / "observed-results.json").write_text(
                        json.dumps(diagnostic_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return runtime_result(reports / label / "results.json", baseline["known_failures"])

            result.unlink(missing_ok=True)
            diagnostic_sidecar.unlink(missing_ok=True)
            try:
                return_code = run(label, [platform / "1cv8", "ENTERPRISE", "/F" + str(db),
                    "/CFormEditorRegression=" + str(result), "/DisableStartupDialogs", "/DisableStartupMessages",
                    "/Out", platform_report], timeout=120, gui=True, allow_nonzero=True)
            except OrchestrationBlocked as error:
                return blocked(str(error))
            if not result.is_file():
                details = diagnostic_text()
                outcome = runtime_process_outcome(return_code, None, details or "1C client exited without producing results.json")
                return blocked(outcome["block_reason"])
            try:
                report = json.loads(result.read_text(encoding="utf-8-sig"))
                test_report.validate_result(report)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                details = diagnostic_text()
                reason = f"1C report is invalid: {error}"
                if details:
                    reason += "; diagnostic: " + details
                outcome = runtime_process_outcome(return_code, None, reason)
                return blocked(outcome["block_reason"])
            details = diagnostic_text()
            outcome = runtime_process_outcome(return_code, report, details)
            if outcome["status"] == "BLOCKED":
                return blocked(outcome["block_reason"], outcome["diagnostic_report"])
            report = outcome["report"]
            report["environment"] = {
                "revision": args.source_revision,
                "dirty": args.source_state == "dirty" if args.source_state != "unknown" else None,
                "platform_version": platform.name,
                "architecture": architecture,
                "target": label,
            }
            result.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            test_report.write_reports(report, reports / label)
            return runtime_result(result, baseline["known_failures"])

        if built:
            check("runtime-cf", lambda: runtime(database, "runtime-cf"))
        if extension_verified:
            check("runtime-cfe", lambda: runtime(host, "runtime-cfe"))

        if args.manual:
            def find_active_display():
                sockets = Path("/tmp/.X11-unix")
                if sockets.is_dir():
                    for socket in sorted(sockets.glob("X[0-9]*")):
                        display = ":" + socket.name[1:]
                        try:
                            active = subprocess.run(["xdpyinfo", "-display", display],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                        except (OSError, subprocess.TimeoutExpired):
                            continue
                        if active.returncode == 0:
                            return display
                raise OrchestrationBlocked("No active VNC/X11 display found for --manual")

            def open_manual_form(db, target):
                display = find_active_display()
                manual_log = reports / ("manual-ui-" + target.lower() + ".log")
                manual_environment = environment.copy()
                manual_environment["DISPLAY"] = display
                with manual_log.open("w") as stream:
                    try:
                        process = subprocess.Popen(
                            [str(platform / "1cv8"), "ENTERPRISE", "/F" + str(db),
                             "/DisableStartupDialogs", "/DisableStartupMessages"],
                            stdout=stream, stderr=subprocess.STDOUT, env=manual_environment,
                            start_new_session=True)
                    except OSError as error:
                        raise OrchestrationBlocked(f"Could not open {target} test form: {error}") from error
                time.sleep(2)
                if process.poll() is not None:
                    detail = manual_log.read_text(encoding="utf-8-sig", errors="replace").strip()[-4000:]
                    raise OrchestrationBlocked(f"{target} UI exited with code {process.returncode}: {detail}")
                return {"name": "manual-ui-" + target.lower(), "status": "passed",
                        "detail": f"FormEditor test form opened on {display}; PID {process.pid}"}

            for target, database_path in (("CF", database), ("CFE", host)):
                if not built or (target == "CFE" and not extension_verified):
                    checks.append({"name": "manual-ui-" + target.lower(), "status": "blocked",
                                   "detail": f"{target} test base is unavailable"})
                    continue
                try:
                    checks.append(open_manual_form(database_path, target))
                except OrchestrationBlocked as error:
                    checks.append({"name": "manual-ui-" + target.lower(), "status": "blocked",
                                   "detail": str(error)})

    if not any(item.get("name") == "ui-cf" for item in checks):
        reason = "CF TestClient UI stage was not reached because an earlier build stage did not complete"
        checks.append({
            "name": "ui-cf", "status": "blocked", "suite_status": "BLOCKED",
            "detail": reason, "block_reason": reason,
            "method_coverage": ui_method_coverage([], project, reason),
            "ui_scenarios": [
                {"id": item["id"], "status": "BLOCKED", "description": item["description"],
                 "expected": "TestClient interaction completed", "actual": "", "error": reason}
                for item in ui_state["scenarios"]
            ],
        })

    decision = release_decision(checks, built, extension_verified,
                                args.allow_known_baseline_failures, args.source_state)
    release_status = decision["status"]
    release_allowed = decision["release_allowed"]
    target_reports = {}
    for target, label in (("CF", "runtime-cf"), ("CFE", "runtime-cfe")):
        result_path = reports / label / "results.json"
        if result_path.is_file():
            target_reports[target] = json.loads(result_path.read_text(encoding="utf-8-sig"))
    environment_report = {
        "revision": args.source_revision,
        "dirty": args.source_state == "dirty" if args.source_state != "unknown" else None,
        "platform_version": platform.name,
        "architecture": architecture,
    }
    aggregate = test_report.aggregate_report(target_reports, checks, environment_report)
    test_report.write_reports(aggregate, reports / "aggregate")
    manifest = {"version": version, "platform_version": platform.name,
                "architecture": architecture,
                "source_revision": args.source_revision,
                "source_state": args.source_state,
                "status": release_status,
                "release_allowed": release_allowed,
                "test_status": aggregate["status"],
                "test_totals": aggregate["totals"],
                "test_report": "reports/aggregate/report.html",
                "release_decision": decision,
                "runtime_baseline": {
                    "id": baseline["id"],
                    "source": baseline.get("source", ""),
                    "known_failure_ids": sorted(baseline["known_failures"]),
                    "known_edt_significant": len(edt_baseline),
                },
                "elapsed_seconds": round(time.time() - started, 2), "checks": checks,
                "source_modules": {str(module.relative_to(project)): hashlib.sha256(module.read_bytes()).hexdigest()
                                   for module in modules.values()}}
    if args.test_only:
        manifest["status"] = aggregate["status"]
        manifest["release_allowed"] = False
        manifest["test_only"] = True
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        exit_code = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[aggregate["status"]]
        totals = aggregate["totals"]
        print(f"TEST {aggregate['status']}: {totals['passed']}/{totals['total']} executions passed "
              f"across {totals['scenarios']} scenarios; report {reports / 'aggregate' / 'report.html'}", flush=True)
        return exit_code
    if not built or not extension_verified:
        manifest["status"] = "build-failed"
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return 5
    shutil.copyfile(original_module, output / "РедакторФорм.bsl")
    shutil.copyfile(project / "README.md", output / "README.md")
    if (project / "CHANGELOG.md").exists():
        shutil.copyfile(project / "CHANGELOG.md", output / "CHANGELOG.md")
    manifest["artifacts"] = {path.name: {"bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    checksum = "".join(f"{item['sha256']}  {name}\n" for name, item in sorted(manifest["artifacts"].items()))
    (output / "SHA256SUMS").write_text(checksum)
    archive = output.parent / f"FormEditor-{version}{'' if release_allowed else '-rc1'}.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(output))
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return decision["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
