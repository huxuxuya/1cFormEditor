import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("test_report", ROOT / "scripts/test_report.py")
test_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_report)


class TestReportValidationTest(unittest.TestCase):
    def setUp(self):
        self.manifest = test_report.load_manifest(ROOT / "tests/scenarios.json")

    def report(self, status="PASS"):
        results = [{
            "id": scenario["id"],
            "status": "PASS",
            "description": scenario["description"],
            "expected": None,
            "actual": None,
            "error": None,
        } for scenario in self.manifest["scenarios"]]
        if status == "FAIL":
            results[0].update(status="FAIL", error="actual assertion failure")
        passed = sum(row["status"] == "PASS" for row in results)
        failed = len(results) - passed
        return {
            "schema_version": 1,
            "suite": self.manifest["suite"],
            "status": "FAIL" if failed else "PASS",
            "environment": {"revision": "abc123", "dirty": True},
            "results": results,
            "totals": {"total": len(results), "passed": passed, "failed": failed},
        }

    def aggregate_inputs(self, cfe=None, cf=None, cfe_check="passed"):
        checks = [{"name": name, "status": "passed"}
                  for name in test_report.REQUIRED_RUN_CHECKS]
        next(row for row in checks if row["name"] == "runtime-cfe")["status"] = cfe_check
        return test_report.aggregate_report(
            {"CF": cf or self.report(), "CFE": cfe or self.report()}, checks,
            {"revision": "abc123", "dirty": True}, self.manifest)

    def test_accepts_complete_pass_and_fail_suites(self):
        passed = test_report.validate_result(self.report(), self.manifest)
        failed = test_report.validate_result(self.report("FAIL"), self.manifest)
        self.assertEqual(passed["status"], "PASS")
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["totals"]["failed"], 1)

    def test_rejects_missing_duplicate_and_unexpected_ids(self):
        report = self.report()
        report["results"].pop()
        report["totals"]["total"] -= 1
        report["totals"]["passed"] -= 1
        with self.assertRaisesRegex(ValueError, "missing="):
            test_report.validate_result(report, self.manifest)

        report = self.report()
        report["results"][1]["id"] = report["results"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicates="):
            test_report.validate_result(report, self.manifest)

        report = self.report()
        report["results"][0]["id"] = "НеожиданныйТест"
        with self.assertRaisesRegex(ValueError, "missing=.*unexpected="):
            test_report.validate_result(report, self.manifest)

    def test_rejects_totals_status_and_record_schema_mismatch(self):
        report = self.report()
        report["totals"]["passed"] -= 1
        with self.assertRaisesRegex(ValueError, "totals"):
            test_report.validate_result(report, self.manifest)

        report = self.report("FAIL")
        report["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "does not match"):
            test_report.validate_result(report, self.manifest)

        report = self.report()
        del report["results"][0]["expected"]
        with self.assertRaisesRegex(ValueError, "missing expected"):
            test_report.validate_result(report, self.manifest)

    def test_blocked_is_an_orchestration_result_without_test_passes(self):
        report = test_report.blocked_report("1C license not available", "abc123", True,
                                            self.manifest["suite"])
        test_report.validate_result(report, self.manifest)
        self.assertIn("BLOCKED", test_report.text_report(report))
        self.assertIn("license", test_report.html_report(report))
        junit = test_report.junit_report(report)
        self.assertIn('tests="1"', junit)
        self.assertIn('errors="1"', junit)
        self.assertIn('type="OrchestrationBlocked"', junit)

        report["results"] = self.report()["results"]
        with self.assertRaisesRegex(ValueError, "no scenario results"):
            test_report.validate_result(report, self.manifest)

    def test_renders_json_text_junit_html_and_escapes_content(self):
        report = self.report("FAIL")
        report["results"][0]["description"] = '<script>alert("x")</script>'
        report["results"][0]["expected"] = "explicit assertion target"
        report["results"][0]["actual"] = "observed value"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            test_report.write_reports(report, output, self.manifest)
            for name in ("results.json", "report.txt", "junit.xml", "report.html"):
                self.assertTrue((output / name).is_file(), name)
            xml = ET.parse(output / "junit.xml").getroot()
            self.assertEqual(xml.attrib["failures"], "1")
            self.assertIn("&lt;script&gt;", (output / "report.html").read_text(encoding="utf-8"))
            self.assertIn("expected", (output / "report.txt").read_text(encoding="utf-8"))

    def test_aggregate_write_emits_one_summary_with_source_and_outcome(self):
        report = self.aggregate_inputs()
        report["environment"].update({
            "revision": "abc123", "dirty": True,
            "configuration_version": "1.0.5.1",
            "platform_version": "8.5.1.1529", "architecture": "arm64",
        })
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            test_report.write_reports(report, output, self.manifest)
            summary = (output / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Test outcome: PASS", summary)
            self.assertIn("`abc123`", summary)
            self.assertIn("1.0.5.1", summary)
            self.assertIn("No release manifest", summary)

    def test_release_tag_summary_requires_matching_clean_source_and_package_hashes(self):
        report = self.aggregate_inputs()
        report["environment"].update({
            "revision": "a" * 40, "dirty": False,
            "configuration_version": "1.0.5.1",
            "platform_version": "8.5.1.1529", "architecture": "arm64",
        })
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            artifacts = output / "artifacts"
            artifacts.mkdir()
            cf = artifacts / "FormEditor.cf"
            cfe = artifacts / "FormEditor.cfe"
            cf.write_bytes(b"cf-test-artifact")
            cfe.write_bytes(b"cfe-test-artifact")
            manifest = {
                "version": "1.0.5.1", "platform_version": "8.5.1.1529",
                "architecture": "arm64", "source_revision": "a" * 40,
                "source_state": "clean", "release_allowed": True,
                "status": "verified", "tag": "1.0.5.1",
                "tag_target_revision": "a" * 40,
                "release_decision": {"status": "verified", "release_allowed": True},
                "test_status": report["status"],
                "test_totals": report["totals"], "artifacts": {
                    path.name: {"bytes": path.stat().st_size,
                                "sha256": test_report._artifact_digest(path)}
                    for path in (cf, cfe)
                },
            }
            verdict = test_report.tag_release_verdict(
                report, manifest, artifacts, "1.0.5.1", "a" * 40)
            self.assertTrue(verdict["validated"], verdict["reasons"])
            summary = test_report.markdown_summary(
                report, manifest, artifacts, "1.0.5.1", "a" * 40)
            self.assertIn("Validated for release `1.0.5.1`", summary)
            self.assertIn("FormEditor.cf", summary)

            manifest["artifacts"]["FormEditor.cf"]["sha256"] = "0" * 64
            verdict = test_report.tag_release_verdict(
                report, manifest, artifacts, "1.0.5.1", "b" * 40)
            self.assertFalse(verdict["validated"])
            failure_text = "\n".join(verdict["reasons"])
            self.assertIn("tag target", failure_text)
            self.assertIn("FormEditor.cf", failure_text)

            mismatched = json.loads(json.dumps(manifest))
            mismatched["version"] = "1.0.5.2"
            verdict = test_report.tag_release_verdict(
                report, mismatched, artifacts, "1.0.5.1", "a" * 40)
            self.assertFalse(verdict["validated"])
            self.assertTrue(any("version" in reason or "tag" in reason for reason in verdict["reasons"]))

    def test_test_only_and_dirty_reports_never_claim_release_validation(self):
        report = self.aggregate_inputs()
        report["environment"].update({
            "revision": "a" * 40, "dirty": True,
            "configuration_version": "1.0.5.1",
            "platform_version": "8.5.1.1529", "architecture": "arm64",
        })
        manifest = {
            "version": "1.0.5.1", "platform_version": "8.5.1.1529",
            "architecture": "arm64", "source_revision": "a" * 40,
            "source_state": "dirty", "release_allowed": False,
            "status": "FAIL", "tag": "1.0.5.1", "tag_target_revision": "a" * 40,
            "release_decision": {"status": "verified", "release_allowed": True},
            "test_only": True, "test_status": report["status"],
            "test_totals": report["totals"], "artifacts": {},
        }
        with tempfile.TemporaryDirectory() as temporary:
            verdict = test_report.tag_release_verdict(
                report, manifest, Path(temporary), "1.0.5.1", "a" * 40)
            self.assertFalse(verdict["validated"])
            self.assertTrue(any("test-only" in reason for reason in verdict["reasons"]))
            summary = test_report.markdown_summary(
                report, manifest, Path(temporary), "1.0.5.1", "a" * 40)
            self.assertIn("candidate/test evidence only", summary)

    def test_missing_runtime_report_is_blocked_by_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                test_report.main([
                    "--input", str(Path(temporary) / "missing.json"),
                    "--output-dir", str(Path(temporary) / "reports"),
                    "--manifest", str(ROOT / "tests/scenarios.json"),
                ])

    def test_aggregate_preserves_two_target_failures_and_totals(self):
        cf = self.report("FAIL")
        cfe = self.report("FAIL")
        checks = [{"name": name, "status": "passed"} for name in test_report.REQUIRED_RUN_CHECKS]
        for name in ("runtime-cf", "runtime-cfe"):
            next(row for row in checks if row["name"] == name)["status"] = "baseline-only"
        report = test_report.aggregate_report({"CF": cf, "CFE": cfe}, checks,
                                              {"revision": "abc123", "dirty": True}, self.manifest)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["totals"], {"total": 60, "passed": 58, "failed": 2, "scenarios": 30})
        self.assertEqual(report["results"][0]["id"], "CF/СозданиеДемонстрации")
        self.assertIn("executions passed across 30 scenarios", test_report.text_report(report))
        self.assertEqual(ET.fromstring(test_report.junit_report(report)).attrib["failures"], "2")
        self.assertIn("CF", test_report.html_report(report))

    def test_aggregate_blocked_target_prevents_green_and_keeps_other_target(self):
        checks = [{"name": name, "status": "passed"} for name in test_report.REQUIRED_RUN_CHECKS]
        next(row for row in checks if row["name"] == "runtime-cfe")["status"] = "blocked"
        report = test_report.aggregate_report({"CF": self.report(), "CFE": None}, checks,
                                              {"revision": "abc123", "dirty": False}, self.manifest)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["totals"]["total"], 30)
        self.assertEqual(report["targets"]["CFE"]["status"], "BLOCKED")
        self.assertIn('type="OrchestrationBlocked"', test_report.junit_report(report))

    def test_ui_coverage_and_blocked_scenarios_render_in_all_aggregate_reports(self):
        checks = [{"name": name, "status": "passed"}
                  for name in test_report.REQUIRED_RUN_CHECKS]
        scenario_manifest = json.loads((ROOT / "tests/ui-scenarios.json").read_text(encoding="utf-8"))
        coverage_manifest = json.loads((ROOT / "tests/ui-method-coverage.json").read_text(encoding="utf-8"))
        reason = "TestManager blocked: Не найдена лицензия"
        ui_check = next(row for row in checks if row["name"] == "ui-cf")
        ui_check.update({
            "status": "blocked", "suite_status": "BLOCKED", "detail": reason,
            "block_reason": reason,
            "method_coverage": [{
                **item, "status": "BLOCKED" if item["required"] else "NOT_APPLICABLE",
                "observed": reason if item["required"] else "helper; no user-interface element",
            } for item in coverage_manifest["methods"]],
            "ui_scenarios": [{
                "id": item["id"], "status": "BLOCKED", "description": item["description"],
                "expected": "TestClient interaction completed", "actual": "", "error": reason,
            } for item in scenario_manifest["scenarios"]],
        })
        report = test_report.aggregate_report(
            {"CF": self.report(), "CFE": self.report()}, checks,
            {"revision": "abc123", "dirty": True}, self.manifest)
        self.assertEqual(report["status"], "BLOCKED")
        text = test_report.text_report(report)
        self.assertIn("UI method coverage:", text)
        self.assertIn("НоваяКнопкаФормы", text)
        self.assertIn("UI_DirectButtonClick", text)
        html = test_report.html_report(report)
        self.assertIn("UI method coverage", html)
        self.assertIn("TestManager blocked", html)
        junit = ET.fromstring(test_report.junit_report(report))
        ui_cases = [case for case in junit.findall("testcase") if case.attrib["name"].startswith("ui:")]
        self.assertEqual(len(ui_cases), 14)
        self.assertTrue(all(case.find("error") is not None for case in ui_cases))
        self.assertIn("лицензия", "".join(ET.tostring(case, encoding="unicode") for case in ui_cases))

    def test_ui_failure_screenshot_link_is_rebased_and_path_is_allowlisted(self):
        checks = [{"name": name, "status": "passed"}
                  for name in test_report.REQUIRED_RUN_CHECKS]
        report = test_report.aggregate_report(
            {"CF": self.report(), "CFE": self.report()}, checks,
            {"revision": "abc123", "dirty": True}, self.manifest)
        ui_check = next(row for row in report["checks"] if row["name"] == "ui-cf")
        scenario_id = "UI_DirectButtonClick"
        screenshot_dir = Path("container-output/reports/ui-cf/screenshots")
        scenario_screenshot = scenario_id + ".png"
        # A one-pixel PNG fixture is enough to verify the artifact path and HTML link.
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_report = root / "container-output/reports/aggregate/results.json"
            source_report.parent.mkdir(parents=True)
            screenshot = root / screenshot_dir / scenario_screenshot
            screenshot.parent.mkdir(parents=True)
            screenshot.write_bytes(png)
            ui_check["ui_scenarios"] = [{
                "id": scenario_id, "status": "FAIL", "description": "button failed",
                "expected": "clicked", "actual": "unchanged", "error": "handler assertion",
                "screenshot": f"../ui-cf/screenshots/{scenario_screenshot}",
            }]
            host_output = root / "reports/aggregate"
            test_report.rebase_ui_screenshot_links(report, source_report, host_output)
            html = test_report.html_report(report)
            expected_href = f"../../container-output/reports/ui-cf/screenshots/{scenario_screenshot}"
            self.assertIn(f'href="{expected_href}"', html)
            self.assertIn("Open PNG", html)
            self.assertEqual(test_report._ui_screenshot_href({
                "id": scenario_id, "screenshot": "../../etc/passwd",
            }), "")

    def test_aggregate_rejects_incomplete_target_report(self):
        partial = self.report()
        partial["results"].pop()
        checks = [{"name": name, "status": "passed"} for name in test_report.REQUIRED_RUN_CHECKS]
        with self.assertRaisesRegex(ValueError, "missing="):
            test_report.aggregate_report({"CF": self.report(), "CFE": partial}, checks,
                                         {}, self.manifest)

    def test_early_container_block_has_full_non_green_aggregate(self):
        report = test_report.blocked_aggregate_report(
            "Docker daemon is unavailable", "container-preflight",
            {"revision": "abc123", "dirty": True}, self.manifest)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["totals"], {"total": 0, "passed": 0, "failed": 0, "scenarios": 30})
        self.assertEqual(report["targets"]["CF"]["status"], "BLOCKED")
        self.assertEqual(report["targets"]["CFE"]["status"], "BLOCKED")
        self.assertEqual(next(item for item in report["checks"]
                              if item["name"] == "python-unit-tests")["status"], "blocked")
        junit = ET.fromstring(test_report.junit_report(report))
        self.assertGreater(int(junit.attrib["errors"]), 0)
        self.assertIn("Docker daemon is unavailable", test_report.text_report(report))

    def test_cli_writes_early_blocked_aggregate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "aggregate"
            result = test_report.main([
                "--aggregate", "--blocked-stage", "edt-compilation",
                "--blocked-reason", "EDT export failed", "--output-dir", str(output),
                "--manifest", str(ROOT / "tests/scenarios.json"),
            ])
            self.assertEqual(result, 2)
            report = test_report.validate_aggregate_result(
                json.loads((output / "results.json").read_text()), self.manifest)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(next(item for item in report["checks"]
                                  if item["name"] == "edt-compilation")["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
