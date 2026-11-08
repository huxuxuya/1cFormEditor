import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class RuntimeReportTest(unittest.TestCase):
    def write_report(self, path, overrides=None, extra=()):
        overrides = overrides or {}
        rows = ["Статус | Проверка | Что проверено и фактический результат"]
        for name in sorted(release.EXPECTED_FORMS | release.EXPECTED_SCENARIOS):
            status, description = overrides.get(name, ("PASS", "Все условия сценария выполнены."))
            rows.append(f"{status} | {name} | {description}")
        rows.extend(extra)
        path.write_text("\n".join(rows), encoding="utf-8-sig")

    def test_accepts_complete_utf8_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            self.write_report(report)
            result = release.runtime_result(report)
            self.assertEqual(result["total"], len(release.EXPECTED_FORMS | release.EXPECTED_SCENARIOS))
            self.assertEqual(result["passed"], result["total"])
            self.assertEqual(result["new_failures"], [])

    def test_classifies_only_matching_platform_baseline_failure_as_known(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            signature = "не пройдено условие «Очистка надписи»"
            self.write_report(report, {"Надпись": ("FAIL", signature)})
            result = release.runtime_result(report, {"Надпись": {"signature": signature, "issue": 6}})
            self.assertEqual(result["known_failures"], ["Надпись"])
            self.assertEqual(result["new_failures"], [])

    def test_new_failure_and_changed_baseline_signature_are_regressions(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            signature = "не пройдено условие «Очистка надписи»"
            self.write_report(report, {
                "Надпись": ("FAIL", signature),
                "КонтекстПослеГруппы": ("FAIL", "Несоответствие типов"),
            })
            result = release.runtime_result(
                report, {"Надпись": {"signature": signature, "issue": 6}})
            self.assertEqual([item["id"] for item in result["new_failures"]], ["КонтекстПослеГруппы"])

            self.write_report(report, {"Надпись": ("FAIL", "Другая ошибка")})
            result = release.runtime_result(
                report, {"Надпись": {"signature": signature, "issue": 6}})
            self.assertEqual([item["id"] for item in result["new_failures"]], ["Надпись"])

    def test_resolved_baseline_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            self.write_report(report)
            result = release.runtime_result(
                report, {"Надпись": {"signature": "known failure", "issue": 6}})
            self.assertEqual(result["resolved_baseline_failures"], ["Надпись"])

    def test_current_arm64_baseline_has_no_new_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            baseline = release.load_runtime_baseline(
                Path(__file__).with_name("release-baseline.json"), "8.5.1.1529", "arm64")
            overrides = {
                name: ("FAIL", failure["signature"])
                for name, failure in baseline["known_failures"].items()
            }
            self.write_report(report, overrides)
            result = release.runtime_result(report, baseline["known_failures"])
            self.assertEqual(len(result["known_failures"]), 14)
            self.assertEqual(result["new_failures"], [])
            self.assertEqual(result["passed"], 12)

    def test_rejects_missing_partial_duplicate_and_failed_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.txt"
            with self.assertRaises(RuntimeError):
                release.runtime_result(report)
            self.write_report(report)
            complete = report.read_text(encoding="utf-8-sig").splitlines()
            incomplete = [line for line in complete if " | ДинамическийСписок | " not in line]
            duplicate = complete + [complete[1]]
            unexpected = complete + ["PASS | НеожиданныйТест | Проверка выполнена."]
            malformed = complete + ["FAIL | ПустоеОписание |   "]
            for lines in [[], complete[:1], incomplete, duplicate, unexpected, malformed]:
                with self.subTest(lines=lines):
                    report.write_text("\n".join(lines), encoding="utf-8-sig")
                    with self.assertRaises(RuntimeError):
                        release.runtime_result(report)


class RuntimeBaselineTest(unittest.TestCase):
    def test_baseline_is_scoped_to_platform_version_and_architecture(self):
        path = Path(__file__).with_name("release-baseline.json")
        match = release.load_runtime_baseline(path, "8.5.1.1529", "arm64")
        self.assertEqual(len(match["known_failures"]), 14)
        self.assertEqual(match["id"], "8.5.1.1529/arm64")
        self.assertEqual(release.load_runtime_baseline(path, "8.5.1.1529", "x86_64")["known_failures"], {})


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
