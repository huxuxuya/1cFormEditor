# Карта репозитория

[README](../README.md) · [Разработка и проверки](development.md) · [API](api.md)

## Основные пути

| Путь | Назначение |
| --- | --- |
| `FormEditor/` | Актуальный 1С EDT-проект и исходники конфигурации. |
| `FormEditor/src/CommonModules/РедакторФорм/` | Исходный модуль библиотеки. Новые метаданные и модули добавляйте в соответствующие каталоги `FormEditor/src/`. |
| `FormEditor/src/DataProcessors/TestForFormModificator/` | Тестовая обработка и формы встроенных проверок. |
| `tests/` | Python unit tests и `release-baseline.json`; новые fixtures размещайте в `tests/fixtures/`. |
| `legacy/edt-root/` | Сохранённые прежние корневые EDT metadata (`.settings/` и `DT-INF/`). |
| `legacy/vanessa/` | Старый Jenkins/Windows/OneScript runner workflow, конфигурация и BDD-сценарии. |
| `legacy/vanessa/features/` | BDD feature и step definitions; Docker smoke launcher использует этот путь. |
| `legacy/vanessa/config/` | Настройки прежнего OneScript/Vanessa Runner процесса. |
| `scripts/` | Текущие Python-сценарии подготовки/сборки и shell-обёртки. |
| `docker/1c-smoke/` | Smoke Docker image, параметры запуска и контейнерный entrypoint. |
| `docker/1c-release/` | Docker image для полного release gate. |
| `docs/` | Руководства пользователя и разработки. |
| `build/` | Игнорируемые build outputs, отчёты, архивы релиза и локальное окружение. |
| `.local/` | Игнорируемые исследовательские данные и локальная диагностика. |
| `README.md`, `CHANGELOG.md`, `LICENSE` | Входная страница, история изменений и лицензия проекта. |

## Куда добавлять файлы

- Исходники и метаданные 1С — в соответствующем объекте под `FormEditor/src/`.
- Python tests — в `tests/`; повторно используемые fixtures — в `tests/fixtures/`.
- Новые BDD-сценарии smoke — в `legacy/vanessa/features/`: launcher и Docker parameters ссылаются на этот каталог.
- Переносимые команды проекта — в `scripts/`, Docker-файлы — в соответствующий каталог `docker/`.
- Документацию — в `docs/`, добавляя навигационную ссылку из `README.md`.

Пути `FormEditor/` и `legacy/vanessa/features/` используются скриптами,
Docker entrypoint и настройками runner. Обновляйте связанные ссылки при
переносе этих каталогов. Внешняя Jenkins job должна явно загружать
`legacy/vanessa/Jenkinsfile` из SCM.

## Локальные данные

- `build/` игнорируется Git; там могут находиться ценные release outputs,
  пакеты платформы и окружения. Проверяйте содержимое до очистки.
- `.local/` игнорируется Git и используется для локальных research-данных,
  диагностики и отчётов старого runner.
- `docker/1c-smoke/platform/` содержит локальные пакеты платформы; они не
  добавляются в Git.
- Python caches, платформенные пакеты и лицензии исключены из Git.
