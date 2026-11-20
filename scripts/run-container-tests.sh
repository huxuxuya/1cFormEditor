#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="${PYTHON:-python3}"
config="${ONEC_TEST_CONFIG:-$root/.local/unified-testing.json}"

usage() {
    cat <<'EOF'
Run the FormEditor 30-scenario suite against both CF and CFE in the existing
licensed container. Results are saved under build/unified-test-run.DATE-TIME.*/reports/.
The local navigation page is build/index.html; regenerate it from existing runs
without Docker with: python3 scripts/build_index.py

Usage: scripts/run-container-tests.sh [--manual] [--help]
  (default)  Run headless checks and save summary/JSON/text/HTML/JUnit reports.
  --manual   Run the same checks, retain both bases, and open both test forms
             in the active container UI (localhost VNC/noVNC URL is printed).
  --help     Show this help.

Local paths are read from .local/unified-testing.json (or ONEC_TEST_CONFIG).
ONEC_TEST_CONTAINER may override the configured running container name.
This command does not build or recreate containers/images.
EOF
}

manual=false
case "${1:-}" in
    "") ;;
    --manual) manual=true ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

mkdir -p "$root/build"
launch_time="$(date '+%Y-%m-%d_%H-%M-%S')"
run_dir="$(mktemp -d "$root/build/unified-test-run.$launch_time.XXXXXX")"
reports_dir="$run_dir/reports"
mkdir -p "$reports_dir"

run_stage="preflight"
refresh_build_index() {
    local requested_state="$1" stage="$2" exit_code="${3:-}"
    local args=(--build-dir "$root/build" --record-run "$run_dir" --state "$requested_state"
        --stage "$stage" --pid "$$")
    if [[ -n "$exit_code" ]]; then
        args+=(--exit-code "$exit_code")
    fi
    "$python" "$root/scripts/build_index.py" "${args[@]}" \
        >/dev/null 2>>"$run_dir/index-update.log" || true
}

set_run_stage() {
    run_stage="$1"
    refresh_build_index RUNNING "$run_stage"
}

finish_build_index() {
    local command_status=$?
    trap - EXIT
    refresh_build_index AUTO "$run_stage" "$command_status"
    printf 'Build index: %s\n' "$root/build/index.html" >&2
    exit "$command_status"
}

trap finish_build_index EXIT
refresh_build_index RUNNING "$run_stage"

revision=unknown
source_state=unknown
if git -C "$root" rev-parse --verify HEAD >/dev/null 2>&1; then
    revision="$(git -C "$root" rev-parse HEAD)"
    if [[ -z "$(git -C "$root" status --porcelain --untracked-files=all)" ]]; then
        source_state=clean
    else
        source_state=dirty
    fi
fi
product_version=unknown
if [[ -f "$root/FormEditor/src/Configuration/Configuration.mdo" ]]; then
    product_version="$("$python" -c 'import sys,xml.etree.ElementTree as E; root=E.parse(sys.argv[1]).getroot(); print(next((node.text for node in root.iter() if node.tag.rsplit("}",1)[-1]=="version" and node.text), "unknown"))' \
        "$root/FormEditor/src/Configuration/Configuration.mdo")"
fi

config_value() {
    "$python" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], ""))' \
        "$config" "$1"
}

write_blocked() {
    local stage="$1" reason="$2"
    "$python" "$root/scripts/test_report.py" --aggregate --blocked-stage "$stage" \
        --blocked-reason "$reason" --output-dir "$reports_dir/aggregate" \
        --source-revision "$revision" --source-state "$source_state" \
        --product-version "$product_version" \
        >"$run_dir/report-writer.log" 2>&1 || true
    printf 'BLOCKED: %s\nReports: %s\n' "$reason" "$reports_dir/aggregate" >&2
    exit 2
}

[[ -f "$config" ]] || write_blocked container-preflight \
    "Local config is missing: $config"
if ! "$python" -m json.tool "$config" >/dev/null 2>&1; then
    write_blocked container-preflight "Local config is not valid JSON: $config"
fi

edt_home="${EDT_HOME:-$(config_value edt_home)}"
plugin_pool="${EDT_PLUGIN_POOL:-$(config_value edt_plugin_pool)}"
edt_config="$(config_value edt_runtime_config)"
swt_jar="$(config_value swt_jar)"
container="${ONEC_TEST_CONTAINER:-$(config_value container)}"
image="${ONEC_TEST_IMAGE:-$(config_value image)}"
platform_bin="$(config_value platform_bin)"
vnc_url="$(config_value vnc_url)"

for pair in "EDT_HOME:$edt_home" "EDT_PLUGIN_POOL:$plugin_pool" \
    "edt_runtime_config:$edt_config" "swt_jar:$swt_jar" \
    "container:$container" "image:$image" "platform_bin:$platform_bin"; do
    key="${pair%%:*}"
    value="${pair#*:}"
    [[ -n "$value" ]] || write_blocked container-preflight "Missing local config value: $key"
done

[[ -d "$edt_home" ]] || write_blocked container-preflight "EDT installation is unavailable: $edt_home"
[[ -d "$plugin_pool" ]] || write_blocked container-preflight "EDT plugin pool is unavailable: $plugin_pool"
[[ -f "$edt_config/config.ini" && -f "$edt_config/bundles.info" ]] || \
    write_blocked container-preflight "Known-good EDT runtime config is incomplete: $edt_config"
[[ -f "$swt_jar" ]] || write_blocked container-preflight "Linux SWT jar is unavailable: $swt_jar"
command -v docker >/dev/null 2>&1 || write_blocked container-preflight "Docker CLI is unavailable"

if ! docker inspect --format '{{.State.Running}}' "$container" >"$run_dir/container-state.txt" 2>"$run_dir/docker-preflight.log"; then
    write_blocked container-preflight "Cannot inspect configured container; see $run_dir/docker-preflight.log"
fi
if [[ "$(cat "$run_dir/container-state.txt")" != true ]]; then
    write_blocked container-preflight "Configured test container is not running: $container"
fi
if ! docker image inspect "$image" >/dev/null 2>"$run_dir/docker-image.log"; then
    write_blocked container-preflight "Configured local image is unavailable: $image"
fi
if ! docker exec "$container" test -x "$platform_bin/ibcmd" || \
   ! docker exec "$container" test -x "$platform_bin/1cv8"; then
    write_blocked container-preflight "Configured platform binaries are unavailable in $container at $platform_bin"
fi
if [[ "$manual" == true ]]; then
    vnc_mappings="$(docker port "$container" 6080/tcp 2>"$run_dir/docker-vnc-port.log" || true)"
    [[ -n "$vnc_mappings" ]] || write_blocked container-preflight \
        "The existing noVNC port 6080 is not published; container network settings are unchanged"
    while IFS= read -r mapping; do
        case "$mapping" in
            127.0.0.1:6080|\[::1\]:6080) ;;
            *) write_blocked container-preflight \
                "The existing noVNC port is not loopback-only ($mapping); refusing to start the VNC backend" ;;
        esac
    done <<< "$vnc_mappings"
    if ! docker exec "$container" sh -lc \
        'xdpyinfo -display :99 >/dev/null 2>&1 && ss -ltn | grep -F "127.0.0.1:5900" >/dev/null'; then
        if ! docker exec "$container" sh -lc 'command -v x11vnc >/dev/null 2>&1'; then
            write_blocked container-preflight "The existing display :99 has no local VNC backend and x11vnc is unavailable"
        fi
        if ! docker exec -d "$container" sh -lc \
            'exec x11vnc -display :99 -rfbport 5900 -listen 127.0.0.1 -forever -shared -nopw -quiet >/tmp/formeditor-x11vnc-99.log 2>&1'; then
            write_blocked container-preflight "Could not start x11vnc on the existing :99 display"
        fi
        vnc_ready=false
        for attempt in {1..40}; do
            if docker exec "$container" sh -lc 'ss -ltn | grep -F "127.0.0.1:5900" >/dev/null'; then
                vnc_ready=true
                break
            fi
            sleep 0.25
        done
        [[ "$vnc_ready" == true ]] || write_blocked container-preflight \
            "x11vnc did not start on 127.0.0.1:5900; see container /tmp/formeditor-x11vnc-99.log"
    fi
fi

cp -R "$edt_config" "$run_dir/edt-config"
cp "$swt_jar" "$run_dir/swt-linux.jar"
edt_mounts=(-v "$root:/project:ro" -v "$run_dir:/work" -v "$plugin_pool:/pool:ro")
set_run_stage "EDT export and validation"
if ! docker run --rm --entrypoint bash "${edt_mounts[@]}" "$image" \
    /project/docker/1c-release/export-edt.sh export --project /project/FormEditor \
    --configuration-files /work/xml >"$run_dir/edt-export.log" 2>&1; then
    write_blocked edt-compilation "EDT export failed; see $run_dir/edt-export.log"
fi
if ! docker run --rm --entrypoint bash "${edt_mounts[@]}" "$image" \
    /project/docker/1c-release/export-edt.sh validate --project-list /project/FormEditor \
    --file /work/edt-validation.tsv >"$run_dir/edt-validation.log" 2>&1; then
    write_blocked edt-compilation "EDT validation failed; see $run_dir/edt-validation.log"
fi

run_key="$(basename "$run_dir")"
remote_run="/tmp/$run_key"
remote_project="$remote_run/project"
remote_output="$remote_run/output"
COPYFILE_DISABLE=1 tar -C "$root" --exclude='__pycache__' --exclude='*.pyc' \
    -cf "$run_dir/source.tar" FormEditor scripts tests README.md CHANGELOG.md \
    2>"$run_dir/source-tar.log"
if ! docker exec "$container" mkdir -p "$remote_project"; then
    write_blocked container-preflight "Could not prepare unique container workspace $remote_run"
fi
if ! docker cp "$run_dir/source.tar" "$container:$remote_run/source.tar" \
    || ! docker cp "$run_dir/xml" "$container:$remote_run/xml" \
    || ! docker cp "$run_dir/edt-validation.tsv" "$container:$remote_run/edt-validation.tsv"; then
    write_blocked container-preflight "Could not copy current source and EDT export into $container"
fi
if ! docker exec "$container" tar -xf "$remote_run/source.tar" -C "$remote_project" \
    >"$run_dir/source-unpack.log" 2>&1; then
    write_blocked container-preflight "Could not unpack current source in $container"
fi

run_args=(--project "$remote_project" --platform-bin "$platform_bin"
    --export "$remote_run/xml" --edt-report "$remote_run/edt-validation.tsv"
    --output "$remote_output" --source-revision "$revision" --source-state "$source_state"
    --test-only)
if [[ "$manual" == true ]]; then
    run_args+=(--manual)
fi
set_run_stage "CF/CFE runtime and UI tests"
set +e
docker exec -e DISPLAY=:99 "$container" python3 "$remote_project/scripts/release.py" "${run_args[@]}" \
    >"$run_dir/container-run.log" 2>&1
container_exit=$?
set -e

copy_exit=0
set_run_stage "Collect and render reports"
docker cp "$container:$remote_output" "$run_dir/container-output" \
    >"$run_dir/docker-copy.log" 2>&1 || copy_exit=$?
[[ "$copy_exit" == 0 ]] || write_blocked runtime-cf-cfe \
    "Could not retrieve test output from $container (exit $copy_exit); see $run_dir/docker-copy.log"

aggregate_input="$run_dir/container-output/reports/aggregate/results.json"
[[ -f "$aggregate_input" ]] || write_blocked runtime-cf-cfe \
    "Test process exited $container_exit without an aggregate report; see $run_dir/container-run.log"

set +e
"$python" "$root/scripts/test_report.py" --input "$aggregate_input" \
    --output-dir "$reports_dir/aggregate" \
    --artifact-dir "$run_dir/container-output" \
    --release-manifest "$run_dir/container-output/manifest.json" \
    >"$run_dir/report-validation.log" 2>&1
report_exit=$?
set -e
if [[ "$report_exit" -gt 2 ]]; then
    write_blocked runtime-cf-cfe "Aggregate report validation failed; see $run_dir/report-validation.log"
fi
status="$("$python" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("status", "INVALID"))' \
    "$reports_dir/aggregate/results.json")"
expected_exit=2
case "$status" in
    PASS) expected_exit=0 ;;
    FAIL) expected_exit=1 ;;
    BLOCKED) expected_exit=2 ;;
    *) write_blocked runtime-cf-cfe "Invalid aggregate status: $status" ;;
esac
if [[ "$container_exit" -gt 2 || "$container_exit" != "$expected_exit" || "$report_exit" != "$expected_exit" ]]; then
    write_blocked runtime-cf-cfe \
        "Test process/report outcome mismatch (container=$container_exit, report=$report_exit, status=$status); see $run_dir/container-run.log"
fi

printf '%s\n' "TEST $status" \
    "Summary: $reports_dir/aggregate/summary.md" \
    "Report: $reports_dir/aggregate/report.html" \
    "JSON: $reports_dir/aggregate/results.json" \
    "Container output and bases: $run_dir/container-output" \
    "Run logs: $run_dir"
if [[ "$manual" == true ]]; then
    printf 'Manual forms are open in the existing UI: %s\n' "$vnc_url"
fi
exit "$expected_exit"
