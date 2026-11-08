#!/usr/bin/env python3
"""Build and verify FormEditor artifacts with the Linux 1C platform in Docker."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile


MD = "http://v8.1c.ru/8.3/MDClasses"
EXPECTED_FORMS = {"СозданиеДемонстрации", "ПривязкаПоля", "ВидФлажка", "СписокВыбора", "ДействиеКоманды", "ФормаПереименованная", "ФормаНеоднозначная"}
EXPECTED_SCENARIOS = {"ОбщиеПроверки", "ГруппаКнопок", "Надпись", "Команда", "КнопкаПанели", "Гиперссылка", "ГруппаФормы", "ГруппаКолонок", "ПолеРеквизитаФормы", "ПолеШапки", "Флажок", "ОшибкаДубликата", "ДинамическийСписок", "КонтекстПослеГруппы", "КонтекстПослеФлажка", "КонтекстПослеШапки", "КонтекстПослеМногострочногоПоля", "КонтекстПослеОшибки", "ЯвныеСвойства"}
REQUIRED_CHECKS = {
    "edt-compilation", "build-and-verify-cf-cfe", "install-and-verify-cfe",
    "designer-syntax", "runtime-cf", "runtime-cfe",
}


def normalized_module(path):
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def runtime_result(path, known_failures=None):
    if not path.is_file():
        raise RuntimeError("1C did not produce the runtime test report")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    expected = EXPECTED_FORMS | EXPECTED_SCENARIOS
    entries = [line for line in lines if line.startswith(("PASS | ", "FAIL | "))]
    parsed = {}
    malformed = []
    duplicates = []
    for line in entries:
        parts = line.split(" | ", 2)
        if len(parts) != 3 or parts[0] not in {"PASS", "FAIL"}:
            malformed.append(line)
            continue
        status, name, description = parts
        if not description.strip():
            malformed.append(line)
            continue
        if name in parsed:
            duplicates.append(name)
        parsed[name] = {"status": status, "description": description}
    names = set(parsed)
    missing = sorted(expected - names)
    unexpected = sorted(names - expected)
    if malformed or duplicates or missing or unexpected:
        problems = []
        if malformed:
            problems.append("malformed entries: " + "; ".join(malformed))
        if duplicates:
            problems.append("duplicate IDs: " + ", ".join(sorted(set(duplicates))))
        if missing:
            problems.append("missing IDs: " + ", ".join(missing))
        if unexpected:
            problems.append("unexpected IDs: " + ", ".join(unexpected))
        raise RuntimeError("Runtime report is incomplete: " + " | ".join(problems))

    known_failures = known_failures or {}
    known = []
    new = []
    resolved = []
    for name, result in parsed.items():
        baseline = known_failures.get(name)
        if result["status"] == "PASS":
            if baseline:
                resolved.append(name)
        elif baseline and baseline["signature"] in result["description"]:
            known.append(name)
        else:
            new.append({"id": name, "detail": result["description"]})
    return {
        "total": len(parsed),
        "passed": sum(result["status"] == "PASS" for result in parsed.values()),
        "known_failures": sorted(known),
        "new_failures": new,
        "resolved_baseline_failures": sorted(resolved),
    }


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
    expected = EXPECTED_FORMS | EXPECTED_SCENARIOS
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
    args = parser.parse_args()
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
    started = time.time()
    environment = os.environ.copy()
    environment["PATH"] = str(platform) + os.pathsep + environment.get("PATH", "")
    # 1C's bundled libstdc++ predates Ubuntu's current WebKit build.
    for library in (Path("/usr/lib/aarch64-linux-gnu/libstdc++.so.6"),
                    Path("/usr/lib/x86_64-linux-gnu/libstdc++.so.6")):
        if library.is_file():
            environment["LD_PRELOAD"] = str(library)
            break

    def run(label, command, timeout=180, gui=False):
        log = reports / (label + ".log")
        print(label, flush=True)
        command_environment = environment
        xvfb = None
        xvfb_log = None
        try:
            if gui:
                command_environment = environment.copy()
                command_environment["DISPLAY"] = ":99"
                xvfb_log = (reports / (label + "-xvfb.log")).open("w")
                xvfb = subprocess.Popen(
                    ["Xvfb", command_environment["DISPLAY"], "-screen", "0", "1280x1024x24",
                     "-nolisten", "tcp", "-ac"], stdout=xvfb_log, stderr=subprocess.STDOUT)
                for _ in range(100):
                    if xvfb.poll() is not None:
                        raise RuntimeError(f"Xvfb exited with code {xvfb.returncode}")
                    ready = subprocess.run(
                        ["xdpyinfo"], env=command_environment,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                    if ready.returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Xvfb did not become ready within 10 seconds")
            with log.open("w") as stream:
                result = subprocess.run([str(part) for part in command], stdout=stream,
                                        stderr=subprocess.STDOUT, env=command_environment,
                                        timeout=timeout)
        finally:
            if xvfb is not None:
                xvfb.terminate()
                try:
                    xvfb.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    xvfb.kill()
                    xvfb.wait()
            if xvfb_log is not None:
                xvfb_log.close()
        if result.returncode:
            details = log.read_text(encoding="utf-8-sig", errors="replace").strip()[-2000:]
            raise RuntimeError(f"{label} exited with code {result.returncode}; see {log}\n{details}")

    def ib(label, *arguments):
        run(label, [platform / "ibcmd", *arguments])

    def check(label, operation):
        try:
            result = operation()
        except Exception as error:
            blocked = "лицензи" in str(error).lower() or "license" in str(error).lower()
            status = "blocked" if blocked else "failed"
            checks.append({"name": label, "status": status, "detail": str(error)})
            print(f"{status.upper()} {label}: {error}", flush=True)
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
            checks.append({"name": label, "status": "passed", **result})
            return True
        if isinstance(result, dict):
            checks.append({"name": label, "status": "passed", **result})
        else:
            checks.append({"name": label, "status": "passed"})
        return True

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
    with tempfile.TemporaryDirectory(prefix="formeditor-release-") as temporary:
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

        def runtime(db, label):
            result = reports / (label + ".txt")
            platform_report = reports / (label + "-platform.txt")
            try:
                run(label, [platform / "1cv8", "ENTERPRISE", "/F" + str(db),
                    "/CFormEditorRegression=" + str(result), "/DisableStartupDialogs", "/DisableStartupMessages",
                    "/Out", platform_report], timeout=120, gui=True)
            except RuntimeError:
                if platform_report.exists():
                    raise RuntimeError(platform_report.read_text(encoding="utf-8-sig", errors="replace"))
                raise
            if not result.exists() and platform_report.exists():
                raise RuntimeError(platform_report.read_text(encoding="utf-8-sig", errors="replace"))
            return runtime_result(result, baseline["known_failures"])

        if built:
            check("runtime-cf", lambda: runtime(database, "runtime-cf"))
        if extension_verified:
            check("runtime-cfe", lambda: runtime(host, "runtime-cfe"))

    decision = release_decision(checks, built, extension_verified,
                                args.allow_known_baseline_failures, args.source_state)
    release_status = decision["status"]
    release_allowed = decision["release_allowed"]
    manifest = {"version": version, "platform_version": platform.name,
                "architecture": architecture,
                "source_revision": args.source_revision,
                "source_state": args.source_state,
                "status": release_status,
                "release_allowed": release_allowed,
                "runtime_baseline": {
                    "id": baseline["id"],
                    "source": baseline.get("source", ""),
                    "known_failure_ids": sorted(baseline["known_failures"]),
                    "known_edt_significant": len(edt_baseline),
                },
                "elapsed_seconds": round(time.time() - started, 2), "checks": checks,
                "source_modules": {str(module.relative_to(project)): hashlib.sha256(module.read_bytes()).hexdigest()
                                   for module in modules.values()}}
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
