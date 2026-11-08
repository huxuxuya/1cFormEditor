#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

check_toolchain() {
    printf '%s\n' '== OneScript =='
    oscript -version
    printf '%s\n' '== Vanessa Runner =='
    vrunner --version
    printf '%s\n' '== Xvfb =='
    xvfb-run -a --server-args='-screen 0 1600x1200x24 -ac' \
        sh -ec 'xdpyinfo >/dev/null; printf "Xvfb display is ready: %s\n" "$DISPLAY"'
}

if [[ "${1:-}" == "toolchain-check" ]]; then
    check_toolchain
    exit 0
fi

if [[ ! -d /opt/1c-packages ]] || ! compgen -G '/opt/1c-packages/*.deb' >/dev/null; then
    fail 'Linux .deb-пакеты платформы 1С не подключены. Поместите полный комплект платформы 8.5.1 в docker/1c-smoke/platform/ и повторите запуск.'
fi

printf '%s\n' '== Installing the mounted 1C platform packages =='
PLATFORM_RELEASE="${PLATFORM_RELEASE:-8.5.1.1343}"
if [[ "$(dpkg --print-architecture)" == arm64 ]]; then
    dpkg --add-architecture amd64
    sed -i '/^deb http:\/\/ports\.ubuntu\.com\/ubuntu-ports\//s/^deb /deb [arch=arm64] /' /etc/apt/sources.list
    cat > /etc/apt/sources.list.d/ubuntu-amd64.list <<'EOF'
deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy main restricted universe multiverse
deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy-updates main restricted universe multiverse
deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy-backports main restricted universe multiverse
deb [arch=amd64] http://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse
EOF
fi
apt-get update
if [[ "$(dpkg --print-architecture)" == arm64 ]]; then
    apt-get install -y --no-install-recommends \
        libc6:amd64 libgcc-s1:amd64 libstdc++6:amd64 zlib1g:amd64 \
        libwebkit2gtk-4.0-37:amd64 libgtk-3-0:amd64 libxtst6:amd64 \
        libxrender1:amd64 libfontconfig1:amd64 libnss3:amd64 \
        libasound2:amd64 libenchant-2-2:amd64 libsm6:amd64 libice6:amd64
fi
PLATFORM_DEBS=()
if [[ -n "${EDT_EXPORT_DIR:-}" ]]; then
    for DEB in /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-*_amd64.deb; do
        [[ -f "$DEB" ]] || continue
        PACKAGE_NAME="$(dpkg-deb -f "$DEB" Package)"
        case "$PACKAGE_NAME" in
            *-client|*-client-nls|*-server|*-server-nls|*-common|*-common-nls)
                PLATFORM_DEBS+=("$DEB")
                ;;
        esac
    done
else
    for DEB in \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-common_*_amd64.deb \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-common-nls_*_amd64.deb \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-thin-client_*_amd64.deb \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-thin-client-nls_*_amd64.deb \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-server_*_amd64.deb \
        /opt/1c-packages/1c-enterprise-${PLATFORM_RELEASE}-server-nls_*_amd64.deb; do
        [[ -f "$DEB" ]] && PLATFORM_DEBS+=("$DEB")
    done
fi
[[ "${#PLATFORM_DEBS[@]}" -gt 0 ]] || fail 'В Linux-дистрибутиве не найден клиентский комплект .deb для выбранного режима.'
dpkg -i "${PLATFORM_DEBS[@]}" || apt-get install -f -y

if [[ "$(dpkg --print-architecture)" == arm64 ]]; then
    for BUNDLED_LIBSTDCXX in /opt/1cv8/x86_64/*/libstdc++.so.6; do
        [[ -e "$BUNDLED_LIBSTDCXX" ]] || continue
        ln -sf /lib/x86_64-linux-gnu/libstdc++.so.6 "$BUNDLED_LIBSTDCXX"
    done
fi

if ! command -v 1cv8c >/dev/null 2>&1; then
    CLIENT_PATH="$(find /opt/1cv8 -type f -name 1cv8c -print -quit 2>/dev/null || true)"
    [[ -n "$CLIENT_PATH" ]] || fail 'После установки пакетов не найден тонкий клиент 1cv8c.'
    export PATH="$(dirname "$CLIENT_PATH"):$PATH"
fi
if ! command -v 1cv8 >/dev/null 2>&1; then
    DESIGNER_PATH="$(find /opt/1cv8 -type f -name 1cv8 -print -quit 2>/dev/null || true)"
    [[ -n "$DESIGNER_PATH" ]] && export PATH="$(dirname "$DESIGNER_PATH"):$PATH"
fi
CLIENT_PATH="$(command -v 1cv8c || true)"

mkdir -p /reports
chmod a+rwx /reports

IB_DIR=/tmp/formeditor-smoke-ib
rm -rf "$IB_DIR"

if [[ -n "${EDT_EXPORT_DIR:-}" ]]; then
    [[ -f "$EDT_EXPORT_DIR/Configuration.xml" ]] || fail "В EDT-экспорте не найден Configuration.xml: $EDT_EXPORT_DIR"
    command -v 1cv8 >/dev/null 2>&1 || fail 'Для создания ИБ из EDT-экспорта нужен пакет конфигуратора (команда 1cv8).'

    printf '%s\n' '== Creating a fresh file infobase =='
    1cv8 CREATEINFOBASE "File=$IB_DIR"

    printf '%s\n' '== Loading configuration from EDT export =='
    1cv8 DESIGNER "/F$IB_DIR" /LoadConfigFromFiles "$EDT_EXPORT_DIR" -Format Hierarchical /Out /reports/load-config.log

    printf '%s\n' '== Updating database configuration =='
    1cv8 DESIGNER "/F$IB_DIR" /UpdateDBCfg /Out /reports/update-dbcfg.log
elif [[ -n "${INFOBASE_DIR:-}" ]]; then
    [[ -f "$INFOBASE_DIR/1Cv8.1CD" ]] || fail "В каталоге ИБ не найден 1Cv8.1CD: $INFOBASE_DIR"
    printf '%s\n' '== Copying the supplied infobase into the container =='
    mkdir -p "$IB_DIR"
    cp -a "$INFOBASE_DIR/." "$IB_DIR/"
else
    fail 'Задайте EDT_EXPORT_DIR для сборки новой ИБ или INFOBASE_DIR для прогона уже собранной ИБ.'
fi

[[ -f "$IB_DIR/1Cv8.1CD" ]] || fail 'Платформа не создала файл ИБ 1Cv8.1CD.'
[[ -f /workspace/project/features/run_full_test.feature ]] || fail 'Не найден features/run_full_test.feature в примонтированном проекте.'
IBSRV_PATH="$(find /opt/1cv8 -type f -name ibsrv -print -quit 2>/dev/null || true)"
[[ -n "$IBSRV_PATH" ]] || fail 'Для файловой ИБ и тонкого клиента нужен пакет Linux-платформы с ibsrv.'

PLATFORM_VERSION="${PLATFORM_VERSION:-8.5.1}"
printf '== Running Vanessa BDD on platform %s ==\n' "$PLATFORM_VERSION"
set +e
xvfb-run -a --server-args='-screen 0 1600x1200x24 -ac' \
    vrunner test vanessa \
      --ibconnection "/F$IB_DIR" \
      --v8version "$PLATFORM_VERSION" \
      --ibsrv \
      --feature-path /workspace/project/features/run_full_test.feature \
      --bddrunner-path /opt/onescript/lib/add/bddRunner.epf \
      --vanessasettings /opt/formeditor/VBParams.json \
      --workspace /workspace/project \
      --report-format junit \
      --report-format allure \
      --report-format cucumberjson \
      --report-path /reports
RESULT=$?
set -e

printf 'Vanessa Runner exit code: %s\n' "$RESULT"
printf 'Reports and logs: /reports\n'
exit "$RESULT"
