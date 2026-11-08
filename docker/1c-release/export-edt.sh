#!/usr/bin/env bash
set -Eeuo pipefail
# /pool: the installed EDT plugin pool, read-only. /work: a fresh working directory.
launcher="$(find /pool -maxdepth 1 -name 'org.eclipse.equinox.launcher_*.jar' | sort | tail -1)"
[[ -n "$launcher" ]] || { echo 'Eclipse launcher is missing' >&2; exit 2; }
display=:99
Xvfb "$display" -screen 0 1280x1024x24 -nolisten tcp -ac >/work/xvfb.log 2>&1 &
xvfb_pid=$!
cleanup_xvfb() {
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup_xvfb EXIT
export DISPLAY="$display"
for attempt in {1..100}; do
    if ! kill -0 "$xvfb_pid" 2>/dev/null; then
        cat /work/xvfb.log >&2
        echo 'Xvfb exited before becoming ready' >&2
        exit 3
    fi
    if xdpyinfo >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
xdpyinfo >/dev/null 2>&1 || {
    cat /work/xvfb.log >&2
    echo 'Xvfb did not become ready within 10 seconds' >&2
    exit 3
}
java \
    --add-opens=java.base/java.lang.constant=ALL-UNNAMED \
    --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.base/java.lang.ref=ALL-UNNAMED \
    --add-opens=java.base/java.nio=ALL-UNNAMED \
    --add-opens=java.base/java.time=ALL-UNNAMED \
    --add-opens=java.base/sun.nio.ch=ALL-UNNAMED \
    --add-opens=java.base/java.net=ALL-UNNAMED -Xmx3g \
    -Declipse.ignoreApp=true -Dosgi.noShutdown=true \
    -Dgosh.args=file:/work/edt-config/startup.txt \
    -jar "$launcher" -configuration /work/edt-config -data /work/edt-workspace \
    -consoleLog -command "$@"
