#!/usr/bin/env python3
"""Validate and render the canonical runtime test report."""

import argparse
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "scenarios.json"
REQUIRED_RUN_CHECKS = (
    "container-preflight", "python-unit-tests", "edt-compilation",
    "build-and-verify-cf-cfe", "install-and-verify-cfe", "designer-syntax",
    "ui-cf", "runtime-cf", "runtime-cfe",
)
RUNTIME_CHECKS = {"runtime-cf", "runtime-cfe"}
OPTIONAL_RUN_CHECKS = {"manual-ui-cf", "manual-ui-cfe"}


def _ui_screenshot_href(record):
    scenario_id = record.get("id")
    if not isinstance(scenario_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", scenario_id):
        return ""
    allowed_paths = {
        f"../ui-cf/screenshots/{scenario_id}.png",
        f"../../container-output/reports/ui-cf/screenshots/{scenario_id}.png",
    }
    for field in ("screenshot_href", "screenshot"):
        value = record.get(field)
        if isinstance(value, str) and value in allowed_paths:
            return value
    return ""


def rebase_ui_screenshot_links(report, input_report, output_dir):
    """Rebase copied container-artifact links for the host aggregate HTML."""
    input_report = Path(input_report).resolve()
    output_dir = Path(output_dir).resolve()
    for check in report.get("checks", []):
        for record in check.get("ui_scenarios", []):
            scenario_id = record.get("id")
            raw_path = record.get("screenshot")
            if (not isinstance(scenario_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", scenario_id)
                    or raw_path != f"../ui-cf/screenshots/{scenario_id}.png"):
                continue
            target = (input_report.parent / raw_path).resolve()
            allowed_dir = (input_report.parent.parent / "ui-cf" / "screenshots").resolve()
            if target.parent != allowed_dir or not target.is_file():
                continue
            href = os.path.relpath(target, output_dir).replace(os.sep, "/")
            expected = f"../../container-output/reports/ui-cf/screenshots/{scenario_id}.png"
            if href == expected:
                record["screenshot_href"] = href


def load_manifest(path=DEFAULT_MANIFEST):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported scenario manifest schema")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Scenario manifest must contain a non-empty scenarios list")
    ids = [item.get("id") for item in scenarios]
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Every scenario must have a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("Scenario manifest contains duplicate IDs")
    if any(not isinstance(item.get("description"), str) or not item["description"].strip()
           for item in scenarios):
        raise ValueError("Every scenario must have a non-empty description")
    return manifest


def blocked_report(reason, revision="unknown", dirty=None, suite="FormEditor"):
    if not reason or not str(reason).strip():
        raise ValueError("A blocked report requires a reason")
    return {
        "schema_version": 1,
        "suite": suite,
        "status": "BLOCKED",
        "block_reason": str(reason).strip(),
        "environment": {"revision": revision, "dirty": dirty},
        "results": [],
        "totals": {"total": 0, "passed": 0, "failed": 0},
    }


def validate_result(report, manifest=None):
    manifest = manifest or load_manifest()
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("Unsupported or invalid test result schema")
    if report.get("suite") != manifest.get("suite"):
        raise ValueError("Test result suite does not match the manifest")
    status = report.get("status")
    if status == "BLOCKED":
        if not isinstance(report.get("block_reason"), str) or not report["block_reason"].strip():
            raise ValueError("BLOCKED report must include block_reason")
        if report.get("results") != [] or report.get("totals") != {"total": 0, "passed": 0, "failed": 0}:
            raise ValueError("BLOCKED report must have no scenario results")
        return report
    if status not in {"PASS", "FAIL"}:
        raise ValueError("Suite status must be PASS, FAIL, or orchestration BLOCKED")

    expected = {item["id"] for item in manifest["scenarios"]}
    records = report.get("results")
    if not isinstance(records, list):
        raise ValueError("Test result must contain a results list")
    parsed = {}
    duplicates = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every test record must be an object")
        for key in ("id", "status", "description", "expected", "actual", "error"):
            if key not in record:
                raise ValueError(f"Test record is missing {key}")
        test_id = record["id"]
        if not isinstance(test_id, str) or not test_id:
            raise ValueError("Test record id must be a non-empty string")
        if test_id in parsed:
            duplicates.append(test_id)
        if record["status"] not in {"PASS", "FAIL"}:
            raise ValueError(f"Invalid status for {test_id}: {record['status']!r}")
        if not isinstance(record["description"], str) or not record["description"].strip():
            raise ValueError(f"Missing description for {test_id}")
        for key in ("expected", "actual", "error"):
            if record[key] is not None and not isinstance(record[key], str):
                raise ValueError(f"{key} must be a string or null for {test_id}")
        parsed[test_id] = record

    missing = sorted(expected - set(parsed))
    unexpected = sorted(set(parsed) - expected)
    if duplicates or missing or unexpected:
        raise ValueError("Invalid runtime IDs: " + "; ".join(filter(None, [
            "duplicates=" + ",".join(sorted(set(duplicates))) if duplicates else "",
            "missing=" + ",".join(missing) if missing else "",
            "unexpected=" + ",".join(unexpected) if unexpected else "",
        ])))

    totals = report.get("totals")
    passed = sum(record["status"] == "PASS" for record in records)
    failed = len(records) - passed
    if totals != {"total": len(records), "passed": passed, "failed": failed}:
        raise ValueError("Test totals do not match the result records")
    expected_status = "PASS" if failed == 0 else "FAIL"
    if status != expected_status:
        raise ValueError(f"Suite status {status} does not match records ({expected_status})")
    return report


def aggregate_report(targets, checks, environment=None, manifest=None):
    """Combine the same scenario suite run against CF and CFE plus preflight checks."""
    manifest = manifest or load_manifest()
    if not isinstance(targets, dict):
        raise ValueError("Aggregate report requires CF and CFE target reports")
    normalized_targets = {}
    for target in ("CF", "CFE"):
        report = targets.get(target)
        if report is None:
            report = blocked_report(f"{target} runtime report was not produced", suite=manifest["suite"])
        normalized_targets[target] = validate_result(report, manifest)

    if not isinstance(checks, list):
        raise ValueError("Aggregate report checks must be a list")
    by_name = {}
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("Every aggregate check requires a name")
        if item["name"] in by_name:
            raise ValueError(f"Duplicate aggregate check: {item['name']}")
        by_name[item["name"]] = item
    for name in REQUIRED_RUN_CHECKS:
        by_name.setdefault(name, {"name": name, "status": "blocked", "detail": "Required check was not completed"})
    unexpected_checks = set(by_name) - set(REQUIRED_RUN_CHECKS) - OPTIONAL_RUN_CHECKS
    if unexpected_checks:
        raise ValueError("Unexpected aggregate checks: " + ", ".join(sorted(unexpected_checks)))
    normalized_checks = [by_name[name] for name in REQUIRED_RUN_CHECKS]
    normalized_checks.extend(by_name[name] for name in sorted(set(by_name) & OPTIONAL_RUN_CHECKS))

    results = []
    for target, report in normalized_targets.items():
        for record in report["results"]:
            results.append({**record, "id": f"{target}/{record['id']}", "target": target})
    totals = {
        "total": len(results),
        "passed": sum(record["status"] == "PASS" for record in results),
        "failed": sum(record["status"] == "FAIL" for record in results),
        "scenarios": len(manifest["scenarios"]),
    }
    has_block = (any(report["status"] == "BLOCKED" for report in normalized_targets.values())
                 or any(item.get("status") == "blocked" for item in normalized_checks))
    has_failure = (any(report["status"] == "FAIL" for report in normalized_targets.values())
                   or any(item.get("status") in {"failed", "baseline-only"} for item in normalized_checks))
    status = "BLOCKED" if has_block else "FAIL" if has_failure else "PASS"
    aggregate = {
        "schema_version": 1,
        "suite": manifest["suite"],
        "status": status,
        "environment": environment or {},
        "checks": normalized_checks,
        "targets": normalized_targets,
        "results": results,
        "totals": totals,
    }
    validate_aggregate_result(aggregate, manifest)
    return aggregate


def blocked_aggregate_report(reason, stage="container-preflight", environment=None, manifest=None):
    """Create a complete aggregate when orchestration stops before runtime."""
    manifest = manifest or load_manifest()
    if stage not in REQUIRED_RUN_CHECKS:
        raise ValueError(f"Unknown blocked pipeline stage: {stage}")
    checks = []
    if stage != "container-preflight":
        checks.append({"name": "container-preflight", "status": "passed",
                       "detail": "Owner wrapper started"})
    checks.append({"name": stage, "status": "blocked", "detail": str(reason)})
    return aggregate_report({"CF": None, "CFE": None}, checks, environment, manifest)


def validate_aggregate_result(report, manifest=None):
    manifest = manifest or load_manifest()
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("Unsupported or invalid aggregate report schema")
    if report.get("suite") != manifest.get("suite"):
        raise ValueError("Aggregate report suite does not match the manifest")
    targets = report.get("targets")
    if not isinstance(targets, dict) or set(targets) != {"CF", "CFE"}:
        raise ValueError("Aggregate report must contain CF and CFE targets")
    for target in ("CF", "CFE"):
        validate_result(targets[target], manifest)
    checks = report.get("checks")
    check_names = [item.get("name") for item in checks] if isinstance(checks, list) else []
    if (check_names[:len(REQUIRED_RUN_CHECKS)] != list(REQUIRED_RUN_CHECKS)
            or len(check_names) != len(set(check_names))
            or set(check_names[len(REQUIRED_RUN_CHECKS):]) - OPTIONAL_RUN_CHECKS):
        raise ValueError("Aggregate report is missing required pipeline checks")
    allowed = {"passed", "baseline-only", "failed", "blocked"}
    if any(item.get("status") not in allowed for item in checks):
        raise ValueError("Aggregate report contains an invalid pipeline check status")

    expected_results = []
    for target in ("CF", "CFE"):
        for record in targets[target]["results"]:
            expected_results.append({**record, "id": f"{target}/{record['id']}", "target": target})
    results = report.get("results")
    if not isinstance(results, list) or results != expected_results:
        raise ValueError("Aggregate execution records do not match the CF/CFE target reports")
    totals = {
        "total": len(expected_results),
        "passed": sum(record["status"] == "PASS" for record in expected_results),
        "failed": sum(record["status"] == "FAIL" for record in expected_results),
        "scenarios": len(manifest["scenarios"]),
    }
    if report.get("totals") != totals:
        raise ValueError("Aggregate totals do not match target execution records")
    has_block = (any(targets[target]["status"] == "BLOCKED" for target in targets)
                 or any(item["status"] == "blocked" for item in checks))
    has_failure = (any(targets[target]["status"] == "FAIL" for target in targets)
                   or any(item["status"] in {"failed", "baseline-only"} for item in checks))
    expected_status = "BLOCKED" if has_block else "FAIL" if has_failure else "PASS"
    if report.get("status") != expected_status:
        raise ValueError(f"Aggregate status {report.get('status')} does not match evidence ({expected_status})")
    return report


def validate_report(report, manifest=None):
    return validate_aggregate_result(report, manifest) if isinstance(report, dict) and "targets" in report else validate_result(report, manifest)


def text_report(report):
    if "targets" in report:
        totals = report["totals"]
        rows = [f"{report['status']} | {report['suite']} | {totals['passed']}/{totals['total']} executions passed across {totals['scenarios']} scenarios"]
        rows.append("Pipeline checks:")
        for check in report["checks"]:
            rows.append(f"{check['status'].upper()} | {check['name']} | {check.get('detail') or check.get('suite_status') or ''}")
            if check.get("method_coverage"):
                rows.append("UI method coverage:")
                rows.extend(
                    f"{item['status']} | {item['method']} | {item['scenario'] or '-'} | {item['relationship']} | {item['observed']}"
                    for item in check["method_coverage"]
                )
            if check.get("ui_scenarios"):
                rows.append("UI scenarios:")
                rows.extend(
                    f"{item['status']} | {item['id']} | expected={item['expected']} | actual={item['actual']} | error={item['error']}"
                    + (" | screenshot=" + _ui_screenshot_href(item) if _ui_screenshot_href(item) else "")
                    + (" | screenshot_error=" + str(item["screenshot_error"]) if item.get("screenshot_error") else "")
                    for item in check["ui_scenarios"]
                )
        rows.append("Target executions:")
        rows.extend(f"{record['status']} | {record['id']} | {record['description']}"
                    + ("; error: " + record['error'] if record['error'] else "")
                    for record in report["results"])
        for target, target_report in report["targets"].items():
            if target_report["status"] == "BLOCKED":
                rows.append(f"BLOCKED | {target} | {target_report['block_reason']}")
        return "\n".join(rows) + "\n"
    totals = report["totals"]
    rows = [f"{report['status']} | {report['suite']} | {totals['passed']}/{totals['total']} passed"]
    if report["status"] == "BLOCKED":
        rows.append("BLOCKED | orchestration | " + report["block_reason"])
        return "\n".join(rows) + "\n"
    for record in report["results"]:
        detail = record["description"]
        if record["expected"]:
            detail += "; expected: " + record["expected"]
        if record["actual"]:
            detail += "; actual: " + record["actual"]
        if record["error"]:
            detail += "; error: " + record["error"]
        rows.append(f"{record['status']} | {record['id']} | {detail}")
    return "\n".join(rows) + "\n"


def junit_report(report):
    if "targets" in report:
        failures = sum(record["status"] == "FAIL" for record in report["results"])
        errors = 0
        testcase_count = len(report["results"])
        for target, target_report in report["targets"].items():
            if target_report["status"] == "BLOCKED":
                errors += 1
                testcase_count += 1
        pipeline_checks = [item for item in report["checks"] if item["name"] not in RUNTIME_CHECKS]
        failures += sum(item["status"] == "failed" for item in pipeline_checks)
        errors += sum(item["status"] == "blocked" for item in pipeline_checks)
        ui_scenario_rows = [scenario for item in report["checks"]
                            for scenario in item.get("ui_scenarios", [])]
        failures += sum(item["status"] == "FAIL" for item in ui_scenario_rows)
        errors += sum(item["status"] == "BLOCKED" for item in ui_scenario_rows)
        testcase_count += len(pipeline_checks) + len(ui_scenario_rows)
        suite = ET.Element("testsuite", name=report["suite"], tests=str(testcase_count),
                           failures=str(failures), errors=str(errors), skipped="0")
        for check in pipeline_checks:
            case = ET.SubElement(suite, "testcase", name="check:" + check["name"], classname=report["suite"])
            if check["status"] == "failed":
                ET.SubElement(case, "failure", message=check.get("detail", "Pipeline check failed"),
                              type="PipelineFailure")
            elif check["status"] == "blocked":
                ET.SubElement(case, "error", message=check.get("detail", "Pipeline check blocked"),
                              type="OrchestrationBlocked")
        for scenario in ui_scenario_rows:
            case = ET.SubElement(suite, "testcase", name="ui:" + scenario["id"], classname=report["suite"])
            if scenario["status"] == "FAIL":
                failure_text = scenario.get("description", "")
                screenshot_href = _ui_screenshot_href(scenario)
                if screenshot_href:
                    failure_text += "\nScreenshot: " + screenshot_href
                elif scenario.get("screenshot_error"):
                    failure_text += "\nScreenshot capture failed: " + str(scenario["screenshot_error"])
                ET.SubElement(case, "failure", message=scenario.get("error") or scenario.get("actual") or "UI assertion failed",
                              type="UIAssertionFailure").text = failure_text
            elif scenario["status"] == "BLOCKED":
                reason = scenario.get("error") or next(
                    (item.get("block_reason") or item.get("detail") for item in report["checks"]
                     if item.get("name") == "ui-cf"), "UI suite did not run")
                ET.SubElement(case, "error", message=reason, type="UIExecutionBlocked")
        for target, target_report in report["targets"].items():
            if target_report["status"] == "BLOCKED":
                case = ET.SubElement(suite, "testcase", name=target + ":orchestration", classname=report["suite"])
                ET.SubElement(case, "error", message=target_report["block_reason"], type="OrchestrationBlocked")
        for record in report["results"]:
            case = ET.SubElement(suite, "testcase", name=record["id"], classname=report["suite"])
            if record["status"] == "FAIL":
                message = record["error"] or record["actual"] or "Scenario failed"
                ET.SubElement(case, "failure", message=message, type="AssertionError").text = record["description"]
        return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"
    if report["status"] == "BLOCKED":
        suite = ET.Element("testsuite", name=report["suite"], tests="1", failures="0", errors="1", skipped="0")
        ET.SubElement(suite, "testcase", name="orchestration")
        ET.SubElement(suite.find("testcase"), "error", message=report["block_reason"], type="OrchestrationBlocked")
    else:
        totals = report["totals"]
        suite = ET.Element("testsuite", name=report["suite"], tests=str(totals["total"]),
                           failures=str(totals["failed"]), skipped="0")
        for record in report["results"]:
            case = ET.SubElement(suite, "testcase", name=record["id"], classname=report["suite"])
            if record["status"] == "FAIL":
                message = record["error"] or record["actual"] or "Scenario failed"
                ET.SubElement(case, "failure", message=message, type="AssertionError").text = record["description"]
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def html_report(report):
    if "targets" in report:
        status = escape(report["status"])
        totals = report["totals"]
        body = ["<h2>Pipeline checks</h2><table><thead><tr><th>Status</th><th>Check</th><th>Detail</th></tr></thead><tbody>"]
        for check in report["checks"]:
            detail = check.get("detail") or check.get("suite_status") or ""
            body.append(f"<tr class=\"{escape(check['status'].lower())}\"><td>{escape(check['status'])}</td><td>{escape(check['name'])}</td><td>{escape(str(detail))}</td></tr>")
        body.append("</tbody></table>")
        for check in report["checks"]:
            coverage = check.get("method_coverage", [])
            if coverage:
                body.append("<h2>UI method coverage</h2><table><thead><tr><th>Status</th><th>Method</th><th>Scope</th><th>Scenario</th><th>Relation</th><th>Observed</th></tr></thead><tbody>")
                for item in coverage:
                    cells = [item["status"], item["method"], item["scope"], item["scenario"] or "-",
                             item["relationship"], item["observed"]]
                    body.append("<tr class=\"" + escape(item["status"].lower()) + "\">" +
                                "".join("<td>" + escape(str(cell)) + "</td>" for cell in cells) + "</tr>")
                body.append("</tbody></table>")
            ui_scenarios = check.get("ui_scenarios", [])
            if ui_scenarios:
                body.append("<h2>Native TestClient UI scenarios</h2><table><thead><tr><th>Status</th><th>ID</th><th>Description</th><th>Expected</th><th>Actual</th><th>Error</th><th>Screenshot</th></tr></thead><tbody>")
                for item in ui_scenarios:
                    cells = [item["status"], item["id"], item.get("description", ""),
                             item.get("expected", ""), item.get("actual", ""), item.get("error", "")]
                    screenshot_href = _ui_screenshot_href(item)
                    if screenshot_href:
                        screenshot_cell = '<a href="' + escape(screenshot_href, quote=True) + '">Open PNG</a>'
                    elif item.get("screenshot_error"):
                        screenshot_cell = "Unavailable: " + escape(str(item["screenshot_error"]))
                    else:
                        screenshot_cell = ""
                    row = "<tr class=\"" + escape(item["status"].lower()) + "\">"
                    row += "".join("<td>" + escape(str(cell)) + "</td>" for cell in cells)
                    row += "<td>" + screenshot_cell + "</td></tr>"
                    body.append(row)
                body.append("</tbody></table>")
        for target, target_report in report["targets"].items():
            body.append(f"<h2>{escape(target)} — {escape(target_report['status'])}</h2>")
            if target_report["status"] == "BLOCKED":
                body.append('<p class="blocked">' + escape(target_report["block_reason"]) + "</p>")
                continue
            body.append("<table><thead><tr><th>Status</th><th>Scenario</th><th>Description</th><th>Expected</th><th>Actual</th><th>Error</th></tr></thead><tbody>")
            for record in target_report["results"]:
                cells = [record["status"], record["id"], record["description"],
                         record["expected"] or "", record["actual"] or "", record["error"] or ""]
                body.append("<tr class=\"" + record["status"].lower() + "\">" +
                            "".join("<td>" + escape(str(cell)) + "</td>" for cell in cells) + "</tr>")
            body.append("</tbody></table>")
        summary = f"{totals['passed']} of {totals['total']} executions passed across {totals['scenarios']} scenarios"
        return "\n".join(["<!doctype html>", '<html lang="en">',
            "<head><meta charset=\"utf-8\"><title>" + escape(report["suite"]) + " test report</title>",
            "<style>body{font:14px system-ui,sans-serif;margin:2rem;color:#222}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}th,td{border:1px solid #bbb;padding:.45rem;text-align:left;vertical-align:top}.pass,.passed{background:#e9f6ec}.fail,.failed,.blocked{background:#fde9e7}.blocked{padding:1rem}</style></head>",
            "<body><h1>" + escape(report["suite"]) + "</h1><h2>" + status + "</h2><p>" + escape(summary) + "</p>",
            "\n".join(body), "</body></html>", ""])
    status = escape(report["status"])
    totals = report["totals"]
    body = []
    if report["status"] == "BLOCKED":
        body.append('<p class="blocked">' + escape(report["block_reason"]) + "</p>")
    else:
        body.append("<table><thead><tr><th>Status</th><th>ID</th><th>Description</th><th>Expected</th><th>Actual</th><th>Error</th></tr></thead><tbody>")
        for record in report["results"]:
            cells = [record["status"], record["id"], record["description"],
                     record["expected"] or "", record["actual"] or "", record["error"] or ""]
            body.append("<tr class=\"" + record["status"].lower() + "\">" +
                        "".join("<td>" + escape(str(cell)) + "</td>" for cell in cells) + "</tr>")
        body.append("</tbody></table>")
    summary = (report["block_reason"] if report["status"] == "BLOCKED" else
               f"{totals['passed']} passed, {totals['failed']} failed, {totals['total']} total")
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head><meta charset=\"utf-8\"><title>" + escape(report["suite"]) + " test report</title>",
        "<style>body{font:14px system-ui,sans-serif;margin:2rem;color:#222}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.45rem;text-align:left;vertical-align:top}.pass{background:#e9f6ec}.fail,.blocked{background:#fde9e7}.blocked{padding:1rem}code{font-family:monospace}</style></head>",
        "<body><h1>" + escape(report["suite"]) + "</h1><h2>" + status + "</h2><p>" + escape(summary) + "</p>",
        "\n".join(body),
        "</body></html>",
        "",
    ])


def write_reports(report, output_dir, manifest=None):
    report = validate_report(report, manifest)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.txt").write_text(text_report(report), encoding="utf-8")
    (output_dir / "junit.xml").write_text(junit_report(report), encoding="utf-8")
    (output_dir / "report.html").write_text(html_report(report), encoding="utf-8")
    if isinstance(report, dict) and "targets" in report:
        write_summary(report, output_dir)
    return report["status"]


def _md_cell(value):
    if value is None:
        return "unknown"
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("`", "\\`").replace("|", "\\|").replace("\r", " ").replace("\n", " "))


def _artifact_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tag_release_verdict(report, release_manifest, artifact_dir, tag, tag_target_revision):
    """Verify the complete report/manifest/tag/package chain before making a release claim."""
    reasons = []
    environment = report.get("environment") or {}
    manifest = release_manifest if isinstance(release_manifest, dict) else {}

    if report.get("status") not in {"PASS", "FAIL"}:
        reasons.append("aggregate is blocked or incomplete")
    targets = report.get("targets") or {}
    if any(targets.get(name, {}).get("status") not in {"PASS", "FAIL"} for name in ("CF", "CFE")):
        reasons.append("both CF and CFE runtime reports must be complete")

    if not tag:
        reasons.append("no release tag was supplied")
    if not release_manifest:
        reasons.append("release manifest is missing")
    if manifest.get("test_only"):
        reasons.append("the run was test-only")
    if manifest.get("release_allowed") is not True:
        reasons.append("release_allowed is not true")
    decision = manifest.get("release_decision") or {}
    if (manifest.get("status") not in {"verified", "verified_with_baseline"}
            or decision.get("release_allowed") is not True
            or decision.get("status") != manifest.get("status")):
        reasons.append("release decision is missing, inconsistent, or not verified")
    if manifest.get("tag") != tag or manifest.get("tag_target_revision") != tag_target_revision:
        reasons.append("tag evidence differs between invocation and co-located release manifest")
    if manifest.get("source_state") != "clean" or environment.get("dirty") is not False:
        reasons.append("source tree was not recorded clean in both report and manifest")

    revision = manifest.get("source_revision")
    if not revision or revision != environment.get("revision"):
        reasons.append("report and manifest source revisions do not match")
    if not tag_target_revision or tag_target_revision != revision:
        reasons.append("tag target does not resolve to the recorded source revision")

    version = manifest.get("version")
    if not version or version != environment.get("configuration_version"):
        reasons.append("configuration version differs between report and manifest")
    if tag and tag != version:
        reasons.append(f"tag {tag!r} does not exactly match configuration version {version!r}")
    if manifest.get("platform_version") != environment.get("platform_version"):
        reasons.append("platform version differs between report and manifest")
    if manifest.get("architecture") != environment.get("architecture"):
        reasons.append("architecture differs between report and manifest")
    if manifest.get("test_status") != report.get("status"):
        reasons.append("test status differs between report and release manifest")
    if manifest.get("test_totals") != report.get("totals"):
        reasons.append("test totals differ between report and release manifest")

    artifact_records = manifest.get("artifacts") or {}
    artifact_dir = Path(artifact_dir) if artifact_dir else None
    verified_artifacts = {}
    for name in ("FormEditor.cf", "FormEditor.cfe"):
        record = artifact_records.get(name)
        artifact = artifact_dir / name if artifact_dir else None
        if not isinstance(record, dict) or not artifact or not artifact.is_file():
            reasons.append(f"{name} or its manifest digest is missing")
            continue
        actual_sha = _artifact_digest(artifact)
        actual_bytes = artifact.stat().st_size
        if record.get("sha256") != actual_sha or record.get("bytes") != actual_bytes:
            reasons.append(f"{name} does not match its recorded SHA256/size")
        else:
            verified_artifacts[name] = {"sha256": actual_sha, "bytes": actual_bytes}

    return {
        "validated": not reasons,
        "tag": tag,
        "source_revision": revision,
        "tag_target_revision": tag_target_revision,
        "artifacts": verified_artifacts,
        "reasons": reasons,
    }


def markdown_summary(report, release_manifest=None, artifact_dir=None,
                     tag=None, tag_target_revision=None):
    """Render a compact provenance summary; never infer release status from test status."""
    report = validate_report(report)
    environment = report.get("environment") or {}
    manifest = release_manifest if isinstance(release_manifest, dict) else None
    manifest_matches_report = bool(manifest
        and manifest.get("source_revision") == environment.get("revision")
        and manifest.get("source_state") == ("dirty" if environment.get("dirty") is True else "clean"
                                               if environment.get("dirty") is False else "unknown")
        and manifest.get("platform_version") == environment.get("platform_version")
        and manifest.get("architecture") == environment.get("architecture")
        and manifest.get("test_status") == report.get("status")
        and manifest.get("test_totals") == report.get("totals"))
    configuration_version = environment.get("configuration_version")
    if (not configuration_version or configuration_version == "unknown") and manifest_matches_report:
        configuration_version = str(manifest.get("version", "unknown")) + " (from matching manifest)"
    lines = [f"# {report['suite']} validation summary", "",
             f"**Test outcome: {report['status']}**", "",
             "| Evidence | Value |", "|---|---|"]

    lines.extend([
        f"| Configuration version | {_md_cell(configuration_version)} |",
        f"| Source revision | `{_md_cell(environment.get('revision'))}` |",
        f"| Source state | {_md_cell('clean' if environment.get('dirty') is False else 'dirty' if environment.get('dirty') is True else 'unknown')} |",
        f"| 1C platform / architecture | {_md_cell(environment.get('platform_version'))} / {_md_cell(environment.get('architecture'))} |",
        f"| Runtime suite | {report['totals'].get('passed', 0)}/{report['totals'].get('total', 0)} passed; {report['totals'].get('failed', 0)} failed across {report['totals'].get('scenarios', 0)} scenarios |",
    ])

    targets = report.get("targets") or {}
    for target in ("CF", "CFE"):
        target_report = targets.get(target)
        if not target_report:
            continue
        target_totals = target_report.get("totals", {})
        outcome = target_report.get("status", "BLOCKED")
        if outcome == "BLOCKED":
            detail = target_report.get("block_reason", "runtime report missing")
            lines.append(f"| {target} runtime | **BLOCKED** — {_md_cell(detail)} |")
        else:
            lines.append(f"| {target} runtime | {outcome}: {target_totals.get('passed', 0)}/{target_totals.get('total', 0)} passed; {target_totals.get('failed', 0)} failed |")

    ui_check = next((item for item in report.get("checks", []) if item.get("name") == "ui-cf"), None)
    if ui_check:
        ui_status = ui_check.get("suite_status") or ui_check.get("status", "blocked").upper()
        ui_total = ui_check.get("total", 0)
        ui_passed = ui_check.get("passed", 0)
        coverage_total = ui_check.get("coverage_total")
        coverage_passed = ui_check.get("coverage_passed")
        ui_value = f"{ui_status}: {ui_passed}/{ui_total} scenarios"
        if coverage_total is not None:
            ui_value += f"; method coverage {coverage_passed}/{coverage_total}"
        lines.append(f"| Native UI (CF) | {ui_value} |")

    checks = report.get("checks", [])
    known_failures = sum(len(item.get("known_failures", [])) for item in checks)
    new_failures = sum(len(item.get("new_failures", [])) for item in checks)
    if any("known_failures" in item or "new_failures" in item for item in checks):
        lines.append(f"| Release baseline classification | {known_failures} known; {new_failures} new; does not alter test FAIL status |")

    if checks:
        lines.extend(["", "## Pipeline stages", "", "| Stage | Status | Detail |", "|---|---|---|"])
        for item in checks:
            detail = item.get("detail") or item.get("block_reason") or ""
            lines.append(f"| {_md_cell(item.get('name'))} | {_md_cell(item.get('status'))} | {_md_cell(detail)} |")

    failure_rows = []
    for target in ("CF", "CFE"):
        target_report = targets.get(target) or {}
        target_check = next((item for item in checks if item.get("name") == f"runtime-{target.lower()}"), {})
        known_ids = set(target_check.get("known_failures", []))
        for record in target_report.get("results", []):
            if record.get("status") != "FAIL":
                continue
            classification = "known baseline" if record.get("id") in known_ids else "new/unmatched"
            detail = record.get("error") or record.get("actual") or ""
            failure_rows.append(f"- `{target}/{_md_cell(record.get('id'))}` ({classification}): {_md_cell(detail)}")
    ui_failures = []
    if ui_check:
        ui_failures = [record for record in ui_check.get("ui_scenarios", [])
                       if record.get("status") in {"FAIL", "BLOCKED"}]
        for record in ui_failures:
            detail = record.get("error") or record.get("actual") or ""
            failure_rows.append(f"- `UI/{_md_cell(record.get('id'))}` ({_md_cell(record.get('status'))}): {_md_cell(detail)}")
    if failure_rows:
        lines.extend(["", "## Failed scenarios", "", *failure_rows])

    if manifest:
        lines.extend(["", "## Release relationship", ""])
        if tag:
            verdict = tag_release_verdict(report, manifest, artifact_dir, tag, tag_target_revision)
            if verdict["validated"]:
                lines.append(f"**Validated for release `{_md_cell(tag)}`.** Tag, clean source revision, configuration version, report, release manifest, and CF/CFE SHA256/size agree.")
            else:
                lines.append(f"**Tag `{_md_cell(tag)}` is not validated; this is candidate/test evidence only.**")
                lines.extend(f"- {reason}" for reason in verdict["reasons"])
        else:
            lines.append("No release tag was supplied; this report is test/candidate evidence and is not associated with a release tag.")
        lines.append(f"- Release gate: `{_md_cell(manifest.get('status'))}`; `release_allowed={str(manifest.get('release_allowed')).lower()}`.")
        artifacts = manifest.get("artifacts") or {}
        for name in ("FormEditor.cf", "FormEditor.cfe"):
            item = artifacts.get(name)
            if isinstance(item, dict):
                digest = item.get("sha256", "unknown")
                lines.append(f"- `{name}`: `{_md_cell(digest)}` ({item.get('bytes', 'unknown')} bytes).")
    else:
        lines.extend(["", "## Release relationship", "",
                      "No release manifest is present. This is test evidence only; no release/package claim is made."])

    lines.extend(["", "## Reports", "",
                  "- [HTML report](report.html)", "- [JUnit report](junit.xml)",
                  "- [Canonical JSON](results.json)"])
    return "\n".join(lines) + "\n"


def write_summary(report, output_dir, release_manifest=None, artifact_dir=None,
                  tag=None, tag_target_revision=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    content = markdown_summary(report, release_manifest, artifact_dir, tag,
                               tag_target_revision)
    temporary = output_dir / ".summary.md.tmp"
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(output_dir / "summary.md")
    return output_dir / "summary.md"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--blocked-reason")
    parser.add_argument("--aggregate", action="store_true",
                        help="write a complete CF/CFE aggregate for an orchestration block")
    parser.add_argument("--blocked-stage", choices=REQUIRED_RUN_CHECKS, default="container-preflight")
    parser.add_argument("--source-revision", default="unknown")
    parser.add_argument("--source-state", choices=("clean", "dirty", "unknown"), default="unknown")
    parser.add_argument("--product-version", default="unknown")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--release-manifest", type=Path)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    if args.blocked_reason:
        if args.aggregate:
            report = blocked_aggregate_report(args.blocked_reason, args.blocked_stage,
                environment={
                    "revision": args.source_revision,
                    "dirty": args.source_state == "dirty" if args.source_state != "unknown" else None,
                    "configuration_version": args.product_version,
                }, manifest=manifest)
        else:
            report = blocked_report(args.blocked_reason, suite=manifest["suite"])
    else:
        if args.input is None or not args.input.is_file():
            raise FileNotFoundError("Runtime JSON report was not produced")
        report = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if isinstance(report, dict) and "targets" in report:
            rebase_ui_screenshot_links(report, args.input, args.output_dir)
    status = write_reports(report, args.output_dir, manifest)
    release_manifest = None
    if args.release_manifest and args.release_manifest.is_file():
        release_manifest = json.loads(args.release_manifest.read_text(encoding="utf-8-sig"))
    if args.artifact_dir or release_manifest:
        write_summary(report, args.output_dir, release_manifest, args.artifact_dir)
    print(f"{status}: reports written to {args.output_dir}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID REPORT: {error}", file=sys.stderr)
        raise SystemExit(2)
