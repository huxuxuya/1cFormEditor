#!/usr/bin/env bash
set -Eeuo pipefail
platform_executable="$(find /opt/1cv8 -type f -name ibcmd -print -quit)"
[[ -n "$platform_executable" ]] || { echo 'ibcmd is missing' >&2; exit 2; }
platform_bin="$(dirname "$platform_executable")"
[[ -x "$platform_bin/1cv8" ]] || { echo 'Full 1C client is missing' >&2; exit 2; }
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s /project/tests -v
exec python3 /project/scripts/release.py --project /project --platform-bin "$platform_bin" "$@"
