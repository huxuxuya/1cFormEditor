#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${SMOKE_IMAGE_NAME:-formeditor-smoke:local}"
case "$(uname -m)" in
    arm64|aarch64) DEFAULT_DOCKER_PLATFORM=linux/arm64 ;;
    *) DEFAULT_DOCKER_PLATFORM=linux/amd64 ;;
esac
DOCKER_PLATFORM="${SMOKE_DOCKER_PLATFORM:-$DEFAULT_DOCKER_PLATFORM}"
PLATFORM_DEB_DIR="${ONEC_PLATFORM_DEB_DIR:-$ROOT_DIR/docker/1c-smoke/platform}"
PLATFORM_RELEASE="${PLATFORM_RELEASE:-8.5.1.1343}"
PLATFORM_VERSION="${PLATFORM_VERSION:-${PLATFORM_RELEASE%.*}}"
EXPORT_DIR="${EDT_EXPORT_DIR:-}"
INFOBASE_DIR="${INFOBASE_DIR:-}"
REPORT_DIR="${SMOKE_REPORT_DIR:-$ROOT_DIR/build/container-smoke}"

if [[ "${1:-}" == "--check-toolchain" ]]; then
    docker build --platform "$DOCKER_PLATFORM" -t "$IMAGE_NAME" "$ROOT_DIR/docker/1c-smoke"
    docker run --rm --platform "$DOCKER_PLATFORM" "$IMAGE_NAME" toolchain-check
    exit $?
fi

if [[ -z "$EXPORT_DIR" && -z "$INFOBASE_DIR" ]]; then
printf '%s\n' 'ERROR: Задайте EDT_EXPORT_DIR (XML-экспорт EDT) или INFOBASE_DIR (готовая файловая ИБ).' >&2
printf '%s\n' 'Для текущего пробного прогона можно указать INFOBASE_DIR=/tmp/form_ib.' >&2
    exit 2
fi

if [[ ! -d "$PLATFORM_DEB_DIR" ]] || ! find "$PLATFORM_DEB_DIR" -maxdepth 1 -type f -name '*.deb' -print -quit | grep -q .; then
    printf 'ERROR: Нет Linux .deb-пакетов 1С в %s\n' "$PLATFORM_DEB_DIR" >&2
    printf '%s\n' 'Для теста ИБ 8.5.1 нужен Linux-дистрибутив платформы 8.5.1 (как минимум тонкий клиент).' >&2
    printf '%s\n' 'Чтобы пересобирать ИБ из EDT-экспорта, дополнительно нужен комплект с конфигуратором.' >&2
    exit 2
fi

if ! find "$PLATFORM_DEB_DIR" -maxdepth 1 -type f -name "1c-enterprise-${PLATFORM_RELEASE}-*_amd64.deb" -print -quit | grep -q .; then
    printf 'ERROR: В %s нет Linux x86_64 пакетов платформы 1С %s.\n' "$PLATFORM_DEB_DIR" "$PLATFORM_RELEASE" >&2
    printf '%s\n' 'Установленная в контейнер платформой версия должна совпадать с версией, которой создана ИБ.' >&2
    exit 2
fi
if ! find "$PLATFORM_DEB_DIR" -maxdepth 1 -type f -name "1c-enterprise-${PLATFORM_RELEASE}-server_*_amd64.deb" -print -quit | grep -q .; then
    printf 'ERROR: В дистрибутиве 1С %s нет серверного компонента для ibsrv.\n' "$PLATFORM_RELEASE" >&2
    exit 2
fi
if [[ -n "$EXPORT_DIR" ]]; then
    CLIENT_PACKAGE_PATTERN="1c-enterprise-${PLATFORM_RELEASE}-client_*_amd64.deb"
else
    CLIENT_PACKAGE_PATTERN="1c-enterprise-${PLATFORM_RELEASE}-thin-client_*_amd64.deb"
fi
if ! find "$PLATFORM_DEB_DIR" -maxdepth 1 -type f -name "$CLIENT_PACKAGE_PATTERN" -print -quit | grep -q .; then
    printf 'ERROR: В дистрибутиве 1С %s нет клиентского компонента для выбранного режима.\n' "$PLATFORM_RELEASE" >&2
    exit 2
fi

[[ -d "$ROOT_DIR/legacy/vanessa/features" ]] || { printf 'ERROR: Не найден каталог legacy/vanessa/features в %s\n' "$ROOT_DIR" >&2; exit 2; }
mkdir -p "$REPORT_DIR"
rm -f "$REPORT_DIR"/*

docker build --platform "$DOCKER_PLATFORM" -t "$IMAGE_NAME" "$ROOT_DIR/docker/1c-smoke"

RUN_ARGS=(
    --rm
    --platform "$DOCKER_PLATFORM"
    --shm-size=2g
    --network bridge
    -e "PLATFORM_RELEASE=$PLATFORM_RELEASE"
    -e "PLATFORM_VERSION=$PLATFORM_VERSION"
    -v "$ROOT_DIR:/workspace/project:ro"
    -v "$PLATFORM_DEB_DIR:/opt/1c-packages:ro"
    -v "$REPORT_DIR:/reports"
)

if [[ -n "$EXPORT_DIR" ]]; then
    [[ -f "$EXPORT_DIR/Configuration.xml" ]] || { printf 'ERROR: Не найден Configuration.xml в %s\n' "$EXPORT_DIR" >&2; exit 2; }
    RUN_ARGS+=(-e EDT_EXPORT_DIR=/workspace/export -v "$EXPORT_DIR:/workspace/export:ro")
fi

if [[ -n "$INFOBASE_DIR" ]]; then
    [[ -f "$INFOBASE_DIR/1Cv8.1CD" ]] || { printf 'ERROR: Не найден 1Cv8.1CD в %s\n' "$INFOBASE_DIR" >&2; exit 2; }
    RUN_ARGS+=(-e INFOBASE_DIR=/input/infobase -v "$INFOBASE_DIR:/input/infobase:ro")
fi

set +e
docker run "${RUN_ARGS[@]}" "$IMAGE_NAME"
RESULT=$?
set -e

printf 'Container smoke exit code: %s\nReports: %s\n' "$RESULT" "$REPORT_DIR"
exit "$RESULT"
