#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="${PYTHON:-python3}"
tag=""
usage() {
    cat <<'EOF'
Run the local 1C release gate.

Usage: scripts/run-container-release.sh [--tag RELEASE_TAG] [--help]
  --tag RELEASE_TAG  Resolve this existing local Git tag and record whether
                     this exact clean build validates for that tag.
  --help             Show this help.

The release summary is written beside the aggregate reports. This command does
not publish or upload artifacts.
EOF
}
while (($#)); do
    case "$1" in
        --tag)
            (($# >= 2)) || { usage >&2; exit 2; }
            tag="$2"
            [[ -n "$tag" ]] || { printf 'Release tag must not be empty.\n' >&2; exit 2; }
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *) usage >&2; exit 2 ;;
    esac
done
if [[ -z "${ONEC_PACKAGE_DIR:-}" || -z "${EDT_HOME:-}" || -z "${EDT_PLUGIN_POOL:-}" ]]; then
    printf 'Set ONEC_PACKAGE_DIR, EDT_HOME and EDT_PLUGIN_POOL before running the release gate.\n' >&2
    exit 3
fi
image="${RELEASE_IMAGE:-formeditor-release:local}"
source_revision=unknown
source_state=unknown
if git -C "$root" rev-parse --verify HEAD >/dev/null 2>&1; then
    source_revision="$(git -C "$root" rev-parse HEAD)"
    if [[ -z "$(git -C "$root" status --porcelain --untracked-files=all)" ]]; then
        source_state=clean
    else
        source_state=dirty
    fi
fi
tag_target_revision=""
if [[ -n "$tag" ]]; then
    git -C "$root" check-ref-format "refs/tags/$tag" >/dev/null 2>&1 || {
        printf 'Invalid release tag name: %s\n' "$tag" >&2
        exit 2
    }
    if ! tag_target_revision="$(git -C "$root" rev-parse --verify "refs/tags/${tag}^{commit}" 2>/dev/null)"; then
        printf 'Release tag does not resolve to a commit: %s\n' "$tag" >&2
        exit 2
    fi
fi
mkdir -p "$root/build"
launch_time="$(date '+%Y-%m-%d_%H-%M-%S')"
work="$(mktemp -d "$root/build/release-run.$launch_time.XXXXXX")"
mkdir -p "$work/context/platform"
printf 'Build reports and artifacts: %s\n' "$work"

run_stage="prepare build context"
refresh_build_index() {
    local requested_state="$1" stage="$2" exit_code="${3:-}"
    local args=(--build-dir "$root/build" --record-run "$work" --state "$requested_state"
        --stage "$stage" --pid "$$")
    if [[ -n "$exit_code" ]]; then
        args+=(--exit-code "$exit_code")
    fi
    "$python" "$root/scripts/build_index.py" "${args[@]}" \
        >/dev/null 2>>"$work/index-update.log" || true
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

cp "$root/docker/1c-release/Dockerfile" "$work/context/Dockerfile"
for component in common server client; do
    found=false
    for package in "$ONEC_PACKAGE_DIR"/*-"$component"_*_*.deb; do
        [[ -f "$package" ]] || continue
        cp "$package" "$work/context/platform/"
        found=true
    done
    $found || { printf 'Missing %s package in %s\n' "$component" "$ONEC_PACKAGE_DIR" >&2; exit 3; }
done
case "$(uname -m)" in
    arm64|aarch64) swt_arch=aarch64 ;;
    *) swt_arch=x86_64 ;;
esac
if ! curl --fail --location --silent --show-error \
    "https://repo.maven.apache.org/maven2/org/eclipse/platform/org.eclipse.swt.gtk.linux.$swt_arch/3.124.200/org.eclipse.swt.gtk.linux.$swt_arch-3.124.200.jar" \
    --output "$work/swt-linux.jar"; then
    printf 'Could not download Linux SWT for EDT; see build output in %s\n' "$work" >&2
    exit 3
fi
if ! python3 "$root/scripts/prepare-edt-runtime.py" "$EDT_HOME" "$work/edt-config" "$work/swt-linux.jar"; then
    printf 'Could not prepare EDT runtime from %s\n' "$EDT_HOME" >&2
    exit 3
fi
set_run_stage "Docker image build"
if ! docker build -t "$image" "$work/context" > "$work/docker-build.log" 2>&1; then
    printf 'Docker image build failed; see %s/docker-build.log\n' "$work" >&2
    exit 3
fi
mounts=(-v "$root:/project:ro" -v "$work:/work" -v "$EDT_PLUGIN_POOL:/pool:ro")
for command in export validate; do
    set_run_stage "EDT $command"
    arguments=(--project /project/FormEditor --configuration-files /work/xml)
    [[ "$command" == export ]] || arguments=(--project-list /project/FormEditor --file /work/edt-validation.tsv)
    if ! docker run --rm --entrypoint bash "${mounts[@]}" "$image" \
        /project/docker/1c-release/export-edt.sh "$command" "${arguments[@]}" > "$work/edt-$command.log" 2>&1; then
        printf 'EDT %s failed; see %s/edt-%s.log\n' "$command" "$work" "$command" >&2
        exit 1
    fi
done
license_mount=()
if [[ -n "${ONEC_LICENSE_DIR:-}" ]]; then
    license_mount=(-v "$ONEC_LICENSE_DIR:/var/1C/licenses:ro")
fi
release_flags=()
case "${ALLOW_KNOWN_BASELINE_FAILURES:-false}" in
    true) release_flags+=(--allow-known-baseline-failures) ;;
    false|'') ;;
    *) printf 'ALLOW_KNOWN_BASELINE_FAILURES must be true or false\n' >&2; exit 2 ;;
esac
if [[ -n "$tag" ]]; then
    release_flags+=(--tag "$tag" --tag-target-revision "$tag_target_revision")
fi
set_run_stage "release gate and package"
if docker run --rm "${mounts[@]}" "${license_mount[@]}" "$image" "${release_flags[@]}" \
    --source-revision "$source_revision" --source-state "$source_state" \
    --export /work/xml --edt-report /work/edt-validation.tsv --output /work/release \
    > "$work/release.log" 2>&1; then
    printf 'Release manifest: %s/release/manifest.json\n' "$work"
    printf 'Release summary: %s/release/reports/aggregate/summary.md\n' "$work"
    printf 'Release log: %s/release.log\n' "$work"
else
    release_exit=$?
    printf 'Release gate exited %s; log: %s/release.log\n' "$release_exit" "$work" >&2
    [[ ! -f "$work/release/reports/aggregate/summary.md" ]] || \
        printf 'Partial release summary: %s/release/reports/aggregate/summary.md\n' "$work" >&2
    exit "$release_exit"
fi
