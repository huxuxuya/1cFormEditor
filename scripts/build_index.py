#!/usr/bin/env python3
"""Generate a local, stable navigation page for build artifacts."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD_DIR = REPO_ROOT / "build"
RUN_STATE_FILE = ".run-state.json"
RUN_TIME_IN_NAME = re.compile(r"^(?:unified-test-run|release-run)\.(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def process_is_running(pid) -> bool:
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError, OSError):
        return False


def resolved_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def file_href(build_dir: Path, path: Path):
    if not path.is_file() or not resolved_inside(build_dir, path):
        return None
    rel = path.resolve().relative_to(build_dir.resolve()).as_posix()
    return quote(rel, safe="/._-()")


def link(build_dir: Path, path: Path, label: str):
    href = file_href(build_dir, path)
    if href is None:
        return ""
    return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'


def file_time(path: Path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def timestamp_in_name(name: str):
    match = RUN_TIME_IN_NAME.match(name)
    if not match:
        return None
    try:
        # The runner writes this timestamp in the host's local timezone.
        return datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S").astimezone(timezone.utc)
    except ValueError:
        return None


def display_time(value):
    when = parse_iso(value) if isinstance(value, str) else value
    if when is None:
        return "время неизвестно"
    return when.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def output_dirs(build_dir: Path):
    try:
        return sorted((path for path in build_dir.iterdir() if path.is_dir()), key=lambda p: p.name)
    except OSError:
        return []


def run_state(path: Path):
    state = read_json(path / RUN_STATE_FILE)
    if isinstance(state, dict) and state.get("schema_version") == 1:
        return state
    return None


def write_run_state(build_dir: Path, run_dir: Path, state: dict):
    if not resolved_inside(build_dir, run_dir) or not run_dir.is_dir():
        raise ValueError(f"Run directory must be inside build/: {run_dir}")
    path = run_dir / RUN_STATE_FILE
    tmp = run_dir / (RUN_STATE_FILE + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def test_report_path(run_dir: Path):
    path = run_dir / "reports" / "aggregate" / "results.json"
    if path.is_file():
        return path
    return None


def release_manifest_path(run_dir: Path):
    direct = run_dir / "manifest.json"
    if direct.is_file():
        return direct
    candidates = [run_dir / name / "manifest.json" for name in
                  ("release", "release-licensed-final", "release-output", "output")]
    return next((path for path in candidates if path.is_file()), None)


def status_from_report(report):
    if not isinstance(report, dict):
        return None
    status = report.get("status")
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        return None
    return status


def is_complete_test_report(report):
    if (not isinstance(report, dict) or report.get("schema_version") != 1
            or report.get("suite") != "FormEditor" or report.get("status") not in {"PASS", "FAIL"}):
        return False
    targets = report.get("targets")
    totals = report.get("totals")
    if not isinstance(targets, dict) or not isinstance(totals, dict):
        return False
    for name in ("CF", "CFE"):
        target = targets.get(name)
        if not isinstance(target, dict) or target.get("status") not in {"PASS", "FAIL"}:
            return False
        rows = target.get("results")
        target_totals = target.get("totals")
        if not isinstance(rows, list) or not isinstance(target_totals, dict):
            return False
        if target_totals.get("total") != len(rows):
            return False
    return totals.get("total") == sum(targets[name]["totals"]["total"] for name in ("CF", "CFE"))


def collect_test_run(build_dir: Path, run_dir: Path):
    state = run_state(run_dir)
    report_path = test_report_path(run_dir)
    report = read_json(report_path) if report_path else None
    status = status_from_report(report)
    totals = report.get("totals", {}) if isinstance(report, dict) else {}
    targets = report.get("targets", {}) if isinstance(report, dict) else {}
    completed_report = is_complete_test_report(report)
    if status in {"PASS", "FAIL"} and not completed_report:
        status = "BLOCKED"
        reason = "Сводный отчёт неполон: CF/CFE results отсутствуют или не совпадают с totals"
    reason = ""
    if status is None and state:
        state_status = state.get("status")
        if state_status == "RUNNING":
            if process_is_running(state.get("pid")):
                status = "RUNNING"
            else:
                status = "INCOMPLETE"
                reason = "Процесс завершился без итогового отчёта"
        elif state_status in {"PASS", "FAIL", "BLOCKED"}:
            status = state_status
        else:
            status = "INCOMPLETE"
    elif status is None:
        status = "INCOMPLETE"
        reason = "Нет сводного отчёта и записи о состоянии запуска"
    elif status == "BLOCKED":
        reason = next((check.get("detail", "") for check in report.get("checks", [])
                       if check.get("status") == "blocked"), "Проверка заблокирована")

    report_time = file_time(report_path) if report_path else None
    started = parse_iso(state.get("started_at")) if state else None
    started = started or timestamp_in_name(run_dir.name)
    order_time = started or report_time or file_time(run_dir)
    completed_time = (parse_iso(state.get("finished_at")) if state else None) or report_time
    stage = state.get("stage", "") if state else ""
    if status == "RUNNING" and stage:
        reason = f"Этап: {stage}"
    if started:
        time_label = "Старт: " + display_time(started)
    elif report_time:
        time_label = "Отчёт: " + display_time(report_time)
    else:
        time_label = "Каталог изменён: " + display_time(order_time)

    screenshots_dir = run_dir / "container-output" / "reports" / "ui-cf" / "screenshots"
    screenshots = []
    if screenshots_dir.is_dir() and resolved_inside(build_dir, screenshots_dir):
        screenshots = sorted((p for p in screenshots_dir.glob("*.png") if p.is_file()), key=lambda p: p.name)

    artifacts = []
    report_dir = run_dir / "reports" / "aggregate"
    for name, label in (("summary.md", "Сводка"), ("report.html", "HTML отчёт"), ("report.txt", "Текст"),
                        ("results.json", "JSON"), ("junit.xml", "JUnit")):
        anchor = link(build_dir, report_dir / name, label)
        if anchor:
            artifacts.append(anchor)
    output_dir = run_dir / "container-output"
    for name, label in (("FormEditor.cf", "CF"), ("FormEditor.cfe", "CFE"),
                        ("manifest.json", "Манифест")):
        anchor = link(build_dir, output_dir / name, label)
        if anchor:
            artifacts.append(anchor)
    test_bases = output_dir / "test-bases"
    for base_name, label in (("main-ib", "База CF"), ("extension-ib", "База CFE"),
                             ("extension-build-ib", "База сборки расширения")):
        anchor = link(build_dir, test_bases / base_name / "1Cv8.1CD", label)
        if anchor:
            artifacts.append(anchor)
    logs = []
    for name in ("container-run.log", "edt-export.log", "edt-validation.log", "report-validation.log",
                 "docker-preflight.log", "docker-image.log"):
        anchor = link(build_dir, run_dir / name, name)
        if anchor:
            logs.append(anchor)

    ui = next((check for check in report.get("checks", []) if check.get("name") == "ui-cf"), {}) \
        if isinstance(report, dict) else {}
    target_summary = []
    for name in ("CF", "CFE"):
        target = targets.get(name) if isinstance(targets, dict) else None
        if isinstance(target, dict):
            t = target.get("totals", {})
            target_summary.append(f'{name}: {t.get("passed", 0)}/{t.get("total", 0)} PASS, {t.get("failed", 0)} FAIL')

    return {
        "name": run_dir.name,
        "kind": "test",
        "status": status,
        "time": order_time,
        "completed_time": completed_time,
        "time_label": time_label,
        "stage": stage,
        "reason": reason,
        "completed_report": completed_report,
        "summary": f'{totals.get("passed", 0)}/{totals.get("total", 0)} выполнено; {totals.get("failed", 0)} FAIL',
        "targets": target_summary,
        "ui": (f'{ui.get("passed", 0)}/{ui.get("total", 0)} UI; '
               f'{ui.get("coverage_passed", 0)}/{ui.get("coverage_total", 0)} методов') if ui else "UI: нет результата",
        "artifacts": artifacts,
        "logs": logs,
        "screenshots": [(p.name, file_href(build_dir, p)) for p in screenshots if file_href(build_dir, p)],
        "report_path": report_dir / "report.html",
    }


def collect_release_run(build_dir: Path, run_dir: Path):
    state = run_state(run_dir)
    manifest_path = release_manifest_path(run_dir)
    manifest = read_json(manifest_path) if manifest_path else None
    if isinstance(manifest, dict) and manifest.get("release_allowed") is True:
        status = "PASS"
        reason = "Манифест разрешает сборку"
    elif isinstance(manifest, dict):
        status = "FAIL"
        reason = str(manifest.get("status", "Сборка не разрешена"))
    elif state and state.get("status") in {"RUNNING", "BLOCKED", "FAIL", "PASS"}:
        status = state["status"]
        reason = state.get("stage", "") if status == "RUNNING" else state.get("reason", "")
        if status == "RUNNING" and not process_is_running(state.get("pid")):
            status = "INCOMPLETE"
            reason = "Процесс завершился без release manifest"
    else:
        status = "INCOMPLETE"
        reason = "Нет итогового release manifest"

    manifest_time = file_time(manifest_path) if manifest_path else None
    started = parse_iso(state.get("started_at")) if state else None
    started = started or timestamp_in_name(run_dir.name)
    order_time = started or manifest_time or file_time(run_dir)
    if started:
        time_label = "Старт: " + display_time(started)
    elif manifest_time:
        time_label = "Manifest: " + display_time(manifest_time)
    else:
        time_label = "Каталог изменён: " + display_time(order_time)

    artifacts = []
    package_dir = manifest_path.parent if manifest_path else run_dir
    candidates = []
    candidates.extend(run_dir.glob("*.zip"))
    candidates.extend(package_dir.glob("*.zip"))
    for name in ("FormEditor.cf", "FormEditor.cfe", "manifest.json", "SHA256SUMS"):
        candidates.append(package_dir / name)
    for path in dict.fromkeys(candidates):
        if not path.is_file() or not resolved_inside(build_dir, path):
            continue
        label = path.name
        if path.suffix.lower() == ".zip":
            label = "RC пакет: " + path.name if "-rc" in path.name.lower() else "Пакет: " + path.name
        artifacts.append(link(build_dir, path, label))
    logs = []
    for name in ("release.log", "release-gate.log", "docker-build.log", "edt-export.log", "edt-validate.log"):
        anchor = link(build_dir, run_dir / name, name)
        if anchor:
            logs.append(anchor)
    for name, label in (("summary.md", "Сводка проверок"), ("report.html", "Тестовый отчёт")):
        report_link = link(build_dir, package_dir / "reports" / "aggregate" / name, label)
        if report_link:
            artifacts.insert(0, report_link)

    return {
        "name": run_dir.name,
        "kind": "release",
        "status": status,
        "time": order_time,
        "time_label": time_label,
        "reason": reason,
        "version": manifest.get("version", "") if isinstance(manifest, dict) else "",
        "artifacts": artifacts,
        "logs": logs,
        "manifest_path": manifest_path,
    }


def status_badge(status):
    labels = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "BLOCKED": "BLOCKED",
        "RUNNING": "В РАБОТЕ",
        "INCOMPLETE": "НЕТ ОТЧЁТА",
    }
    css = status.lower() if status in {"PASS", "FAIL", "BLOCKED", "RUNNING"} else "incomplete"
    return f'<span class="badge {css}">{labels.get(status, "НЕТ ОТЧЁТА")}</span>'


def render_run_card(build_dir: Path, run: dict, latest=False):
    title = "Последний полный прогон" if latest else run["name"]
    parts = [f'<article class="run-card" data-search="{html.escape((run["name"] + " " + run.get("reason", "")).lower(), quote=True)}">']
    parts.append(f'<div class="card-head"><div><h3>{html.escape(title)}</h3><div class="muted">{html.escape(run["name"])} · {html.escape(run["time_label"])}</div></div>{status_badge(run["status"])}</div>')
    if run.get("summary"):
        parts.append(f'<p class="summary">{html.escape(run["summary"])}</p>')
    if run.get("version"):
        parts.append(f'<p class="muted">Версия: {html.escape(str(run["version"]))}</p>')
    if run.get("targets"):
        parts.append('<p class="muted">' + ' · '.join(html.escape(item) for item in run["targets"]) + '</p>')
    if run.get("ui"):
        parts.append(f'<p class="muted">{html.escape(run["ui"])}</p>')
    if run.get("reason"):
        parts.append(f'<p class="reason">{html.escape(run["reason"])}</p>')
    if run.get("artifacts"):
        parts.append('<div class="links">' + ' '.join(run["artifacts"]) + '</div>')
    if run.get("screenshots"):
        parts.append('<details><summary>Ошибки и снимки (' + str(len(run["screenshots"])) + ')</summary><div class="links">')
        parts.extend(f'<a href="{html.escape(href, quote=True)}">{html.escape(name)}</a>' for name, href in run["screenshots"])
        parts.append('</div></details>')
    if run.get("logs"):
        parts.append('<details><summary>Логи</summary><div class="links">' + ' '.join(run["logs"]) + '</div></details>')
    parts.append('</article>')
    return "\n".join(parts)


def scan_runs(build_dir: Path):
    tests = []
    releases = []
    for path in output_dirs(build_dir):
        lowered = path.name.lower()
        if "license" in lowered:
            continue
        if not resolved_inside(build_dir, path):
            continue
        if path.name.startswith("unified-test-run."):
            tests.append(collect_test_run(build_dir, path))
        elif path.name.startswith("release-run."):
            releases.append(collect_release_run(build_dir, path))
    tests.sort(key=lambda item: item["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    releases.sort(key=lambda item: item["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return tests, releases


def render_index(build_dir: Path):
    tests, releases = scan_runs(build_dir)
    completed = [item for item in tests if item["completed_report"]]
    completed.sort(key=lambda item: item["completed_time"] or item["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    latest_complete = completed[0] if completed else None
    latest_attempt = tests[0] if tests else None
    newer_attempt = latest_attempt and latest_complete and latest_attempt["time"] and latest_complete["completed_time"] \
        and latest_attempt["time"] > latest_complete["completed_time"]
    latest_release = releases[0] if releases else None

    body = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FormEditor — build artifacts</title>
<style>
:root{color-scheme:light dark;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{margin:0 auto;padding:24px;max-width:1120px;background:#f4f6f8;color:#202833}h1{margin:0 0 4px}h2{margin:28px 0 12px}h3{margin:0;font-size:17px}.muted{color:#66717e;font-size:13px}.summary{font-weight:650;font-size:18px;margin:14px 0 4px}.reason{color:#784d00;margin:10px 0}.notice{background:#fff6dd;border:1px solid #e8cf84;padding:14px 16px;border-radius:10px;margin:16px 0}.latest{background:#fff;border:1px solid #d8dee5;border-radius:12px;padding:18px;margin:12px 0}.run-card{background:#fff;border:1px solid #d8dee5;border-radius:10px;padding:14px 16px;margin:10px 0}.card-head{display:flex;align-items:start;justify-content:space-between;gap:12px}.badge{font-size:12px;font-weight:750;padding:4px 9px;border-radius:999px;white-space:nowrap}.pass{color:#075f38;background:#d8f2e4}.fail{color:#a11b23;background:#ffe0e2}.blocked,.incomplete{color:#795400;background:#fff0c2}.running{color:#164f93;background:#dcecff}.links{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 2px}.links a{display:inline-block;padding:6px 9px;border-radius:6px;background:#edf2f7;text-decoration:none;color:#1558a6}a:hover{text-decoration:underline}details{margin-top:10px}summary{cursor:pointer;color:#435367}input{width:min(100%,500px);padding:9px 11px;border:1px solid #bec8d2;border-radius:7px;font:inherit}.empty{color:#697583;padding:14px 0}.section-note{font-size:13px;color:#697583}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:10px}@media(prefers-color-scheme:dark){body{background:#171b20;color:#e5e8ec}.latest,.run-card{background:#22282f;border-color:#39414b}.muted,.section-note{color:#aab4c0}.links a{background:#303a46;color:#9cc8ff}.notice{background:#382f1c;border-color:#766328}.reason{color:#f3cf75}.pass{background:#153b2b;color:#b1edcf}.fail{background:#491e23;color:#ffb2b7}.blocked,.incomplete{background:#443718;color:#f8d978}.running{background:#1c344d;color:#b5d9ff}}
</style></head><body>
<h1>FormEditor — артефакты сборок и тестов</h1>
<p class="muted">Локальная навигация по содержимому <code>build/</code>. Каталоги запусков сохранены как есть; суффиксы имён случайные, история отсортирована по времени отчёта/манифеста.</p>
<p><input id="search" type="search" placeholder="Фильтр по имени запуска или статусу" aria-label="Фильтр запусков"></p>
"""]
    if latest_attempt and (not latest_complete or (latest_attempt["time"] and latest_complete["time"] and latest_attempt["time"] > latest_complete["time"])):
        body.append('<div class="notice"><strong>Последняя попытка новее последнего полного отчёта.</strong> Статус не подменяется результатом предыдущего запуска.</div>')
        body.append(render_run_card(build_dir, latest_attempt))
    if latest_complete:
        body.append('<section class="latest"><h2>Последний полный тестовый отчёт</h2>')
        body.append(render_run_card(build_dir, latest_complete, latest=True))
        body.append('</section>')
    else:
        body.append('<div class="notice">Полного отчёта CF+CFE пока нет. Смотрите последнюю попытку и историю ниже.</div>')
    body.append('<h2>Последняя сборка релиза или кандидата</h2>')
    body.append(render_run_card(build_dir, latest_release) if latest_release else '<p class="empty">Release-run пока не найден.</p>')
    body.append('<h2 id="tests">История тестовых прогонов</h2>')
    if tests:
        body.append('<div class="grid">')
        body.extend(render_run_card(build_dir, item) for item in tests)
        body.append('</div>')
    else:
        body.append('<p class="empty">Нет каталогов unified-test-run.*</p>')
    body.append('<h2 id="releases">История release-run</h2>')
    if releases:
        body.append('<div class="grid">')
        body.extend(render_run_card(build_dir, item) for item in releases)
        body.append('</div>')
    else:
        body.append('<p class="empty">Нет каталогов release-run.*</p>')
    release_env = build_dir / "release-env"
    if release_env.is_dir():
        body.append('<h2>Среда сборки</h2><article class="run-card"><h3>release-env/</h3>')
        body.append('<p class="muted">Локальный контекст платформы для сборки Docker image; это кэш/окружение, не пакет релиза.</p>')
        dockerfile_link = link(build_dir, release_env / "Dockerfile", "Dockerfile")
        if dockerfile_link:
            body.append('<div class="links">' + dockerfile_link + '</div>')
        body.append('</article>')
    diagnostic_dirs = [path for path in output_dirs(build_dir)
                       if path.name.startswith("screenshot-smoke-") and resolved_inside(build_dir, path)]
    if diagnostic_dirs:
        body.append('<h2>Отдельные диагностические снимки</h2>')
        for directory in sorted(diagnostic_dirs, key=lambda item: item.name):
            images = sorted((path for path in directory.glob("*.png") if path.is_file()), key=lambda path: path.name)
            if images:
                body.append(f'<article class="run-card"><h3>{html.escape(directory.name)}</h3><div class="links">')
                body.extend(link(build_dir, image_path, image_path.name) for image_path in images)
                body.append('</div></article>')
    body.append('<p class="section-note">Каталоги платформенного окружения и прочие вспомогательные данные не считаются результатами теста или релизными пакетами. Старые запуски без отчёта помечены «Нет отчёта», а не «В работе».</p>')
    body.append('''<script>
const search=document.getElementById('search');search.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();document.querySelectorAll('.run-card').forEach(card=>{card.hidden=!!q&&!card.dataset.search.includes(q)&&!card.innerText.toLowerCase().includes(q)})});
</script></body></html>''')
    return "\n".join(body)


def update_run(build_dir: Path, run_dir: Path, requested_state: str, stage: str, pid: int | None,
               exit_code: int | None, reason: str):
    previous = run_state(run_dir) or {}
    now = iso_now()
    started = previous.get("started_at") or now
    if requested_state == "AUTO":
        if run_dir.name.startswith("unified-test-run."):
            report = read_json(test_report_path(run_dir)) if test_report_path(run_dir) else None
            status = status_from_report(report)
            if status in {"PASS", "FAIL"} and not is_complete_test_report(report):
                status = "BLOCKED"
        else:
            manifest_path = release_manifest_path(run_dir)
            manifest = read_json(manifest_path) if manifest_path else None
            if isinstance(manifest, dict):
                status = "PASS" if manifest.get("release_allowed") is True else "FAIL"
            else:
                status = None
        if status is None:
            status = "BLOCKED" if exit_code not in (None, 0) else "INCOMPLETE"
        requested_state = status
    terminal = requested_state != "RUNNING"
    state = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "kind": "test" if run_dir.name.startswith("unified-test-run.") else "release",
        "status": requested_state,
        "stage": stage or ("finished" if terminal else previous.get("stage", "starting")),
        "started_at": started,
        "updated_at": now,
        "finished_at": now if terminal else None,
        "pid": None if terminal else (pid or previous.get("pid")),
        "exit_code": exit_code,
        "reason": reason or previous.get("reason", ""),
    }
    write_run_state(build_dir, run_dir, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a local HTML index of test and release artifacts.")
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--record-run", type=Path, help="record/update lifecycle state for a run, then regenerate index")
    parser.add_argument("--state", choices=("RUNNING", "PASS", "FAIL", "BLOCKED", "INCOMPLETE", "AUTO"))
    parser.add_argument("--stage", default="")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    build_dir = args.build_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    if args.record_run:
        if not args.state:
            parser.error("--record-run requires --state")
        run_dir = args.record_run.resolve()
        update_run(build_dir, run_dir, args.state, args.stage, args.pid, args.exit_code, args.reason)
    output = build_dir / "index.html"
    temporary = build_dir / ".index.html.tmp"
    temporary.write_text(render_index(build_dir), encoding="utf-8")
    os.replace(temporary, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
