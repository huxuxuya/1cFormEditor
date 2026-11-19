# Карта репозитория

[README](../README.md) · [Разработка и проверки](development.md) ·
[API](api.md)

## Основные пути

| Путь | Назначение |
| --- | --- |
| `FormEditor/` | Актуальный EDT-проект и исходники конфигурации 1С. |
| `FormEditor/src/CommonModules/РедакторФорм/` | Исходник публичного модуля библиотеки. |
| `FormEditor/src/DataProcessors/TestForFormModificator/` | Одна встроенная тестовая обработка; формы запускают те же проверки для AUTO и MANUAL. |
| `tests/` | Python unit tests, `scenarios.json` с 26 runtime ID, UI scenario/method coverage manifests и release baseline. |
| `scripts/` | Owner runner, release orchestrator, report validator/renderers и build/preparation scripts. |
| `scripts/run-container-tests.sh` | Единая команда AUTO и `--manual` для CF/CFE suite. |
| `docker/1c-release/` | Docker entrypoint, EDT export и image для release/test pipeline. |
| `docs/` | Документация API, разработки, release gate и карты репозитория. |
| `legacy/edt-root/` | Сохранённые исторические корневые EDT `.settings/` и `DT-INF/`. |
| `README.md`, `CHANGELOG.md`, `LICENSE` | Входная страница, история изменений и лицензия проекта. |
| `build/` | Игнорируемые локальные экспорты, отчёты, собранные артефакты и test bases. |
| `.local/` | Игнорируемые локальные настройки runner и research/diagnostic данные. |

## Куда добавлять файлы

- Исходники 1С и метаданные — в соответствующем объекте под `FormEditor/src/`.
- Зарегистрированный runtime сценарий добавляйте в тестовую обработку и
  синхронизируйте его ID/описание в `tests/scenarios.json`; Python проверки и
  fixtures размещайте в `tests/` (fixtures — в `tests/fixtures/`).
- Повторно используемые команды и pipeline orchestration размещайте в
  `scripts/`; Docker image files — в `docker/1c-release/`.
- Руководства размещайте в `docs/` и добавляйте навигацию из `README.md`.
- Не размещайте в Git outputs, EDT exports, базы, Linux пакеты платформы и
  локальную конфигурацию машины; для них используются игнорируемые `build/`
  и `.local/`.

Старый Jenkins/Windows/Vanessa runner удалён. Используйте
`scripts/run-container-tests.sh`; актуальные команды и выводы описаны в
[инструкции разработки](development.md).

## Локальные данные

- `build/` игнорируется Git; там могут находиться ценные release artifacts,
  пакеты платформы, test bases и отчёты. Не удаляйте его целиком при очистке.
- `.local/` игнорируется Git и содержит machine-specific runner settings и
  локальные исследовательские/диагностические данные.
- Python caches и платформенные/сборочные артефакты исключены из Git.
- Root metadata в `legacy/edt-root/` сохранены отдельно и не используются
  current build/test scripts.
