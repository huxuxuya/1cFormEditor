import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class RuntimeReportTest(unittest.TestCase):
    def write_report(self, path, overrides=None, mutate=None):
        overrides = overrides or {}
        records = []
        for item in release.test_report.load_manifest()["scenarios"]:
            status, error = overrides.get(item["id"], ("PASS", ""))
            records.append({
                "id": item["id"], "status": status,
                "description": item["description"],
                "expected": "", "actual": "", "error": error,
            })
        report = {
            "schema_version": 1, "suite": "FormEditor",
            "status": "FAIL" if any(row["status"] == "FAIL" for row in records) else "PASS",
            "results": records,
            "totals": {
                "total": len(records),
                "passed": sum(row["status"] == "PASS" for row in records),
                "failed": sum(row["status"] == "FAIL" for row in records),
            },
        }
        if mutate:
            mutate(report)
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return report

    def test_accepts_complete_utf8_json_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            self.write_report(report)
            result = release.runtime_result(report)
            self.assertEqual(result["total"], 26)
            self.assertEqual(result["passed"], result["total"])
            self.assertEqual(result["suite_status"], "PASS")
            self.assertEqual(result["new_failures"], [])

    def test_classifies_known_failure_without_changing_actual_suite_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            error = "Ошибка регрессионной проверки: Очистка надписи"
            self.write_report(report, {"Надпись": ("FAIL", error)})
            result = release.runtime_result(report, {"Надпись": {
                "signature": "Надпись не пройдено условие «Очистка надписи»", "issue": 6}})
            self.assertEqual(result["suite_status"], "FAIL")
            self.assertEqual(result["known_failures"], ["Надпись"])
            self.assertEqual(result["new_failures"], [])
            self.assertEqual(next(row for row in result["results"] if row["id"] == "Надпись")["status"], "FAIL")

    def test_new_failure_and_changed_baseline_signature_are_regressions(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            signature = "Ошибка регрессионной проверки: Очистка надписи"
            self.write_report(report, {
                "Надпись": ("FAIL", signature),
                "КонтекстПослеГруппы": ("FAIL", "Несоответствие типов"),
            })
            result = release.runtime_result(
                report, {"Надпись": {"signature": "Надпись не пройдено условие «Очистка надписи»", "issue": 6}})
            self.assertEqual([item["id"] for item in result["new_failures"]], ["КонтекстПослеГруппы"])

            self.write_report(report, {"Надпись": ("FAIL", "Ошибка регрессионной проверки: Другая ошибка")})
            result = release.runtime_result(
                report, {"Надпись": {"signature": "Надпись не пройдено условие «Очистка надписи»", "issue": 6}})
            self.assertEqual([item["id"] for item in result["new_failures"]], ["Надпись"])

    def test_resolved_baseline_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            self.write_report(report)
            result = release.runtime_result(
                report, {"Надпись": {"signature": "known failure", "issue": 6}})
            self.assertEqual(result["resolved_baseline_failures"], ["Надпись"])

    def test_current_arm64_baseline_has_no_new_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            baseline = release.load_runtime_baseline(
                Path(__file__).with_name("release-baseline.json"), "8.5.1.1529", "arm64")
            overrides = {
                name: ("FAIL", failure["signature"].split("не пройдено условие «", 1)[-1].rstrip("»"))
                for name, failure in baseline["known_failures"].items()
            }
            self.write_report(report, overrides)
            result = release.runtime_result(report, baseline["known_failures"])
            self.assertEqual(len(result["known_failures"]), 14)
            self.assertEqual(result["new_failures"], [])
            self.assertEqual(result["passed"], 12)
            self.assertEqual(result["suite_status"], "FAIL")

    def test_rejects_missing_partial_duplicate_unexpected_and_invalid_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "results.json"
            with self.assertRaises(RuntimeError):
                release.runtime_result(report_path)
            original = self.write_report(report_path)
            invalid_reports = []
            partial = json.loads(json.dumps(original))
            partial["results"].pop()
            invalid_reports.append(partial)
            duplicate = json.loads(json.dumps(original))
            duplicate["results"].append(duplicate["results"][0])
            invalid_reports.append(duplicate)
            unexpected = json.loads(json.dumps(original))
            unexpected["results"][-1]["id"] = "Unexpected"
            invalid_reports.append(unexpected)
            malformed = json.loads(json.dumps(original))
            del malformed["results"][0]["description"]
            invalid_reports.append(malformed)
            wrong_totals = json.loads(json.dumps(original))
            wrong_totals["totals"]["failed"] = 1
            invalid_reports.append(wrong_totals)
            for invalid in invalid_reports:
                with self.subTest(invalid=invalid):
                    report_path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        release.runtime_result(report_path)

            report_path.write_text(json.dumps(release.test_report.blocked_report("runtime timeout")), encoding="utf-8")
            self.assertEqual(release.runtime_result(report_path)["suite_status"], "BLOCKED")

    def test_blocked_report_is_distinct_from_pass_and_has_no_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "results.json"
            report.write_text(json.dumps(release.test_report.blocked_report("client did not start")), encoding="utf-8")
            result = release.runtime_result(report)
            self.assertEqual(result["suite_status"], "BLOCKED")


class UITestReportTest(unittest.TestCase):
    def report(self, status="PASS", actual="clicked:native-ui-test-value"):
        scenarios = json.loads((Path(__file__).parent / "ui-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
        records = [{
            "id": item["id"],
            "status": status,
            "description": item["description"],
            "expected": "observed result",
            "actual": actual if status == "PASS" else "",
            "error": "" if status == "PASS" else "Observed result differs",
        } for item in scenarios]
        return {
            "schema_version": 1,
            "suite": "FormEditor UI",
            "status": status,
            "results": records,
            "totals": {"total": len(records), "passed": len(records) if status == "PASS" else 0,
                       "failed": 0 if status == "PASS" else len(records)},
        }

    def test_validates_actual_input_and_button_result(self):
        report = release.validate_ui_report(self.report())
        self.assertEqual(len(report["results"]), 14)
        self.assertEqual(report["results"][0]["actual"], "clicked:native-ui-test-value")

    def test_ui_failure_remains_a_failure(self):
        report = self.report("FAIL", actual="")
        self.assertEqual(release.validate_ui_report(report)["status"], "FAIL")

    def test_ui_failure_screenshot_path_is_restricted_to_its_scenario(self):
        report = self.report("FAIL", actual="")
        scenario_id = report["results"][0]["id"]
        report["results"][0]["screenshot"] = f"screenshots/{scenario_id}.png"
        self.assertEqual(release.validate_ui_report(report)["results"][0]["screenshot"],
                         f"screenshots/{scenario_id}.png")
        report["results"][0]["screenshot"] = "../../etc/passwd"
        with self.assertRaisesRegex(ValueError, "not allowed"):
            release.validate_ui_report(report)

    def test_missing_unexpected_or_duplicate_ui_scenarios_are_rejected(self):
        report = self.report()
        report["results"][0]["id"] = "UI_StaticControl"
        with self.assertRaisesRegex(ValueError, "IDs"):
            release.validate_ui_report(report)
        report = self.report()
        report["results"].append(dict(report["results"][0]))
        report["totals"] = {"total": 2, "passed": 2, "failed": 0}
        with self.assertRaisesRegex(ValueError, "IDs"):
            release.validate_ui_report(report)

    def test_invalid_ui_totals_and_status_are_rejected(self):
        report = self.report()
        report["totals"]["passed"] = 0
        with self.assertRaisesRegex(ValueError, "totals"):
            release.validate_ui_report(report)
        report = self.report("FAIL", actual="")
        report["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "status"):
            release.validate_ui_report(report)

    def test_ui_method_inventory_matches_all_common_module_exports(self):
        rows = release.ui_method_coverage([], Path(__file__).parents[1], "TestClient unavailable")
        self.assertEqual(len(rows), 22)
        self.assertEqual(sum(row["required"] for row in rows), 20)
        self.assertEqual(sum(row["status"] == "NOT_APPLICABLE" for row in rows), 2)
        self.assertTrue(all(row["status"] == "BLOCKED" for row in rows if row["required"]))

    def test_every_required_export_has_a_scenario_and_direct_or_indirect_relation(self):
        rows = release.ui_method_coverage([], Path(__file__).parents[1], "blocked")
        self.assertTrue(all(row["scenario"] and row["relationship"] in {"direct", "indirect"}
                            for row in rows if row["required"]))

    def test_ui_report_rejects_missing_one_of_the_required_scenarios(self):
        report = self.report()
        report["results"].pop()
        report["totals"]["total"] -= 1
        report["totals"]["passed"] -= 1
        with self.assertRaisesRegex(ValueError, "IDs"):
            release.validate_ui_report(report)

    def test_nonzero_client_exit_blocks_even_with_a_valid_full_report(self):
        report = {"schema_version": 1, "suite": "FormEditor", "status": "PASS",
                  "results": [], "totals": {"total": 0, "passed": 0, "failed": 0}}
        outcome = release.runtime_process_outcome(1, report, "client exited after writing JSON")
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["diagnostic_report"], report)
        self.assertEqual(outcome["diagnostic_report"]["status"], "PASS")

    def test_zero_exit_without_report_is_blocked(self):
        outcome = release.runtime_process_outcome(0, None)
        self.assertEqual(outcome["status"], "BLOCKED")


class RuntimeBaselineTest(unittest.TestCase):
    def test_baseline_is_scoped_to_platform_version_and_architecture(self):
        path = Path(__file__).with_name("release-baseline.json")
        match = release.load_runtime_baseline(path, "8.5.1.1529", "arm64")
        self.assertEqual(len(match["known_failures"]), 14)
        self.assertEqual(match["id"], "8.5.1.1529/arm64")
        self.assertEqual(release.load_runtime_baseline(path, "8.5.1.1529", "x86_64")["known_failures"], {})


class ModuleNormalizationTest(unittest.TestCase):
    def test_utf8_and_windows_1251_exports_compare_after_line_ending_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            utf8 = Path(temporary) / "utf8.bsl"
            cp1251 = Path(temporary) / "cp1251.bsl"
            utf8.write_bytes("Процедура Проверка()\nСообщить(\"Надпись\");\n".encode("utf-8-sig"))
            cp1251.write_bytes("Процедура Проверка()\r\nСообщить(\"Надпись\");\r\n".encode("cp1251"))
            self.assertEqual(release.normalized_module(utf8), release.normalized_module(cp1251))
            cp1251.write_bytes("Процедура Проверка()\r\nСообщить(\"Заголовок\");\r\n".encode("cp1251"))
            self.assertNotEqual(release.normalized_module(utf8), release.normalized_module(cp1251))


class EDTReportTest(unittest.TestCase):
    def row(self, severity, rule="rule", object_name="Object.Module", message="finding"):
        return "\t".join(["2026-11-08T00:00:00Z", severity, "Стандарты кодирования",
                          "FormEditor", rule, object_name, "1", message])

    def test_accepts_only_the_two_recorded_significant_findings(self):
        baseline = release.load_edt_baseline(Path(__file__).with_name("release-baseline.json"))
        rows = [self.row("Значительная", item["rule"], item["object"], item["message"])
                for item in baseline]
        rows.extend([self.row("Незначительная"), self.row("Тривиальная")])
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "edt.tsv"
            report.write_text("\n".join(rows), encoding="utf-8")
            result = release.validate_edt_report(report, baseline)
        self.assertEqual(result["severity_counts"]["Значительная"], 2)
        self.assertEqual(len(result["accepted_significant"]), 2)
        self.assertEqual(result["new_significant"], [])

    def test_new_significant_findings_and_configuration_errors_fail(self):
        for rows in [[self.row("Значительная")], [self.row("Ошибка конфигурации")],
                     ["malformed row"], [self.row("НоваяСерьёзность")]]:
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as temporary:
                report = Path(temporary) / "edt.tsv"
                report.write_text("\n".join(rows), encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    release.validate_edt_report(report, [])

    def test_fixed_significant_findings_are_reported_as_resolved(self):
        baseline = release.load_edt_baseline(Path(__file__).with_name("release-baseline.json"))
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "edt.tsv"
            report.write_text(self.row("Тривиальная"), encoding="utf-8")
            result = release.validate_edt_report(report, baseline)
        self.assertEqual(len(result["resolved_significant"]), 2)


class ReleaseDecisionTest(unittest.TestCase):
    def checks(self, status="passed"):
        return [{"name": name, "status": status}
                for name in sorted(release.REQUIRED_CHECKS)]

    def test_fully_green_clean_run_is_publishable(self):
        self.assertEqual(
            release.release_decision(self.checks(), True, True, False, "clean"),
            {"status": "verified", "release_allowed": True, "exit_code": 0})

    def test_allows_baseline_only_release_only_with_explicit_opt_in(self):
        checks = self.checks()
        next(item for item in checks if item["name"] == "runtime-cf")["status"] = "baseline-only"
        self.assertEqual(
            release.release_decision(checks, True, True, False),
            {"status": "baseline_only", "release_allowed": False, "exit_code": 2})
        self.assertEqual(
            release.release_decision(checks, True, True, True),
            {"status": "verified_with_baseline", "release_allowed": True, "exit_code": 0})

    def test_new_failure_blocked_and_build_failure_never_allow_release(self):
        failing = self.checks()
        failing[0]["status"] = "failed"
        blocked = self.checks()
        blocked[0]["status"] = "blocked"
        for checks, built, extension, expected in [
            (failing, True, True, "candidate"),
            (blocked, True, True, "blocked"),
            (self.checks(), False, False, "build-failed"),
        ]:
            with self.subTest(expected=expected):
                decision = release.release_decision(checks, built, extension, True)
                self.assertEqual(decision["status"], expected)
                self.assertFalse(decision["release_allowed"])

    def test_dirty_unknown_or_incomplete_runs_never_allow_release(self):
        checks = self.checks()
        next(item for item in checks if item["name"] == "runtime-cf")["status"] = "baseline-only"
        for source_state, expected in [("dirty", "source_dirty"), ("unknown", "source_unknown")]:
            with self.subTest(source_state=source_state):
                result = release.release_decision(checks, True, True, True, source_state)
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["release_allowed"])
        result = release.release_decision(checks[:-1], True, True, True)
        self.assertEqual(result["status"], "candidate")
        self.assertFalse(result["release_allowed"])


if __name__ == "__main__":
    unittest.main()
