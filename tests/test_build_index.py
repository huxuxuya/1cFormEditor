import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("build_index", ROOT / "scripts/build_index.py")
build_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_index)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def aggregate(status="PASS"):
    target_status = "FAIL" if status == "FAIL" else "PASS"
    targets = {
        name: {
            "status": target_status,
            "results": [{"id": "one", "status": target_status}],
            "totals": {"total": 1, "passed": int(target_status == "PASS"), "failed": int(target_status == "FAIL")},
        }
        for name in ("CF", "CFE")
    }
    return {
        "schema_version": 1,
        "suite": "FormEditor",
        "status": status,
        "targets": targets,
        "totals": {"total": 2, "passed": 2 if status == "PASS" else 0, "failed": 0 if status == "PASS" else 2},
        "checks": [{"name": "ui-cf", "passed": 1, "total": 1, "coverage_passed": 20, "coverage_total": 20}],
    }


class BuildIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.build = Path(self.temp.name) / "build"
        self.build.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_run(self, name, status="PASS", mtime=1000):
        run = self.build / name
        report = run / "reports" / "aggregate" / "results.json"
        write_json(report, aggregate(status))
        os.utime(report, (mtime, mtime))
        return run

    def test_history_uses_report_time_not_random_suffix_and_separates_running_attempt(self):
        completed = self.write_run("unified-test-run.zzzzz", "PASS", 1000)
        newer_complete = self.write_run("unified-test-run.aaaaa", "FAIL", 2000)
        running = self.build / "unified-test-run.00000"
        running.mkdir()
        state = {
            "schema_version": 1, "status": "RUNNING", "stage": "CF/CFE build",
            "started_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:01+00:00",
            "pid": os.getpid(),
        }
        write_json(running / build_index.RUN_STATE_FILE, state)

        tests, _ = build_index.scan_runs(self.build)
        self.assertEqual(tests[0]["name"], running.name)
        self.assertEqual(tests[0]["status"], "RUNNING")
        completed_runs = [item for item in tests if item["completed_report"]]
        self.assertEqual(completed_runs[0]["name"], newer_complete.name)
        self.assertNotEqual(completed_runs[0]["name"], completed.name)
        page = build_index.render_index(self.build)
        self.assertIn("Последняя попытка новее последнего полного отчёта", page)
        self.assertIn("CF/CFE build", page)
        self.assertIn("FAIL", page)

    def test_old_run_without_report_is_incomplete_not_running(self):
        run = self.build / "unified-test-run.old"
        run.mkdir()
        tests, _ = build_index.scan_runs(self.build)
        self.assertEqual(tests[0]["status"], "INCOMPLETE")
        self.assertIn("Нет отчёта", build_index.render_index(self.build))

    def test_timestamped_run_names_are_readable_and_sort_by_launch_time(self):
        older = self.write_run("unified-test-run.2026-11-20_10-00-00.aaaaaa", "PASS", 3000)
        newer = self.write_run("unified-test-run.2026-11-20_11-00-00.zzzzzz", "PASS", 2000)
        tests, _ = build_index.scan_runs(self.build)
        self.assertEqual(tests[0]["name"], newer.name)
        self.assertTrue(tests[0]["time_label"].startswith("Старт: 2026-11-20 11:00:00"))
        self.assertEqual(tests[1]["name"], older.name)
        release = self.build / "release-run.2026-11-20_12-00-00.bbbbbb"
        write_json(release / "release-licensed-final" / "manifest.json", {
            "version": "1.0.5.1", "status": "verified", "release_allowed": True,
        })
        releases = build_index.scan_runs(self.build)[1]
        self.assertEqual(releases[0]["name"], release.name)
        self.assertTrue(releases[0]["time_label"].startswith("Старт: 2026-11-20 12:00:00"))

    def test_report_details_are_escaped_and_all_links_are_existing_relative_files(self):
        run = self.write_run("unified-test-run.<img src=x>", "FAIL")
        summary = run / "reports" / "aggregate" / "summary.md"
        summary.write_text("# Exact run summary\n", encoding="utf-8")
        output = run / "container-output"
        (output / "reports" / "ui-cf" / "screenshots").mkdir(parents=True)
        (output / "reports" / "ui-cf" / "screenshots" / "UI_case.png").write_bytes(b"png")
        (output / "FormEditor.cf").write_bytes(b"cf")
        page = build_index.render_index(self.build)
        self.assertNotIn('<img src=x>', page)
        self.assertIn("%3Cimg%20src%3Dx%3E", page)
        self.assertIn("Сводка", page)
        hrefs = re.findall(r'href="([^"]+)"', page)
        self.assertTrue(hrefs)
        for href in hrefs:
            target = (self.build / unquote(href)).resolve()
            self.assertTrue(target.is_relative_to(self.build.resolve()), href)
            self.assertTrue(target.is_file(), href)

    def test_release_packages_are_separate_and_candidate_is_labeled(self):
        run = self.build / "release-run.random"
        products = run / "release-licensed-final"
        write_json(products / "manifest.json", {
            "version": "1.0.5.1", "status": "verified_with_baseline", "release_allowed": True,
        })
        summary = products / "reports" / "aggregate" / "summary.md"
        summary.parent.mkdir(parents=True)
        summary.write_text("# Release evidence\n", encoding="utf-8")
        (run / "FormEditor-1.0.5.1-rc1.zip").write_bytes(b"rc")
        (run / "FormEditor-1.0.5.1.zip").write_bytes(b"stable")
        releases = build_index.scan_runs(self.build)[1]
        self.assertEqual(releases[0]["status"], "PASS")
        page = build_index.render_index(self.build)
        self.assertIn("RC пакет: FormEditor-1.0.5.1-rc1.zip", page)
        self.assertIn("Пакет: FormEditor-1.0.5.1.zip", page)
        self.assertIn("Сводка проверок", page)
        self.assertIn("Последняя сборка релиза или кандидата", page)

    def test_record_run_and_regenerate_writes_atomic_index_and_final_status(self):
        run = self.build / "unified-test-run.abc"
        run.mkdir()
        build_index.main(["--build-dir", str(self.build), "--record-run", str(run),
                          "--state", "RUNNING", "--stage", "preflight", "--pid", str(os.getpid())])
        state = json.loads((run / build_index.RUN_STATE_FILE).read_text())
        self.assertEqual(state["status"], "RUNNING")
        started_at = state["started_at"]
        write_json(run / "reports" / "aggregate" / "results.json", aggregate("FAIL"))
        build_index.main(["--build-dir", str(self.build), "--record-run", str(run),
                          "--state", "AUTO", "--exit-code", "1"])
        state = json.loads((run / build_index.RUN_STATE_FILE).read_text())
        self.assertEqual(state["status"], "FAIL")
        self.assertEqual(state["started_at"], started_at)
        self.assertTrue(state["finished_at"])
        self.assertTrue((self.build / "index.html").is_file())
        self.assertFalse((self.build / ".index.html.tmp").exists())

    def test_blocked_shell_runners_record_timestamped_runs_and_refresh_isolated_index(self):
        env = {"PATH": os.environ["PATH"]}

        test_root = Path(self.temp.name) / "test-repository"
        (test_root / "scripts").mkdir(parents=True)
        (test_root / "tests").mkdir()
        for source, target in (
            (ROOT / "scripts/run-container-tests.sh", test_root / "scripts/run-container-tests.sh"),
            (ROOT / "scripts/build_index.py", test_root / "scripts/build_index.py"),
            (ROOT / "scripts/test_report.py", test_root / "scripts/test_report.py"),
            (ROOT / "tests/scenarios.json", test_root / "tests/scenarios.json"),
        ):
            shutil.copy2(source, target)
        test_result = subprocess.run(["bash", str(test_root / "scripts/run-container-tests.sh")],
                                     cwd=test_root, env=env, text=True, capture_output=True)
        self.assertEqual(test_result.returncode, 2, test_result.stderr)
        test_runs = list((test_root / "build").glob("unified-test-run.*"))
        self.assertEqual(len(test_runs), 1)
        self.assertRegex(test_runs[0].name, r"^unified-test-run\.\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.[A-Za-z0-9]+$")
        test_state = json.loads((test_runs[0] / build_index.RUN_STATE_FILE).read_text())
        self.assertEqual(test_state["status"], "BLOCKED")
        self.assertTrue((test_root / "build/index.html").is_file())
        self.assertIn("build/index.html", test_result.stderr)

        release_root = Path(self.temp.name) / "release-repository"
        (release_root / "scripts").mkdir(parents=True)
        (release_root / "docker/1c-release").mkdir(parents=True)
        for source, target in (
            (ROOT / "scripts/run-container-release.sh", release_root / "scripts/run-container-release.sh"),
            (ROOT / "scripts/build_index.py", release_root / "scripts/build_index.py"),
            (ROOT / "docker/1c-release/Dockerfile", release_root / "docker/1c-release/Dockerfile"),
        ):
            shutil.copy2(source, target)
        release_env = dict(env, ONEC_PACKAGE_DIR=str(Path(self.temp.name) / "empty-packages"),
                           EDT_HOME=self.temp.name, EDT_PLUGIN_POOL=self.temp.name)
        Path(release_env["ONEC_PACKAGE_DIR"]).mkdir()
        release_result = subprocess.run(["bash", str(release_root / "scripts/run-container-release.sh")],
                                        cwd=release_root, env=release_env, text=True, capture_output=True)
        self.assertEqual(release_result.returncode, 3, release_result.stderr)
        release_runs = list((release_root / "build").glob("release-run.*"))
        self.assertEqual(len(release_runs), 1)
        self.assertRegex(release_runs[0].name, r"^release-run\.\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.[A-Za-z0-9]+$")
        release_state = json.loads((release_runs[0] / build_index.RUN_STATE_FILE).read_text())
        self.assertEqual(release_state["status"], "BLOCKED")
        self.assertTrue((release_root / "build/index.html").is_file())
        self.assertIn("build/index.html", release_result.stderr)


if __name__ == "__main__":
    unittest.main()
