#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
mkdir -p "$root/build"
work="$(mktemp -d "$root/build/release-run.XXXXXX")"
mkdir -p "$work/context/platform"
printf 'Build reports and artifacts: %s\n' "$work"
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
if ! docker build -t "$image" "$work/context" > "$work/docker-build.log" 2>&1; then
    printf 'Docker image build failed; see %s/docker-build.log\n' "$work" >&2
    exit 3
fi
mounts=(-v "$root:/project:ro" -v "$work:/work" -v "$EDT_PLUGIN_POOL:/pool:ro")
for command in export validate; do
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
docker run --rm "${mounts[@]}" "${license_mount[@]}" "$image" "${release_flags[@]}" \
    --source-revision "$source_revision" --source-state "$source_state" \
    --export /work/xml --edt-report /work/edt-validation.tsv --output /work/release \
    > "$work/release.log" 2>&1
