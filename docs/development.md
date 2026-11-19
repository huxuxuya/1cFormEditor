# Разработка и проверки

[README](../README.md) · [Карта репозитория](repository-layout.md) ·
[API](api.md) · [Release gate](release-gate.md)

## Требования

- Python 3.9 или новее для скриптов и unit tests.
- Docker с доступом к настроенному локальному образу и уже запущенному
  контейнеру проверки.
- EDT installation и plugin pool для свежего экспорта текущего проекта.
- Для реального CF/CFE runtime проверок — доступный контейнер с платформой 1С.

Локальные пути для owner runner хранятся в игнорируемом Git файле
`.local/unified-testing.json`. Он должен указывать на EDT, plugin pool, known-good
EDT runtime config/SWT, локальный image и уже работающий контейнер. Файл не
содержит данных лицензии или активации. Переопределить имя контейнера можно
через `ONEC_TEST_CONTAINER`; путь к локальному JSON — через `ONEC_TEST_CONFIG`.

## Python unit tests

Тесты используют стандартную библиотеку Python:

```sh
python3 -m unittest discover -s tests -v
```

Тот же unit suite запускается как обязательная стадия контейнерной проверки и
попадает в общий pipeline report.

## Единый runner CF/CFE

Одна команда экспортирует текущий EDT-проект, собирает и проверяет CF/CFE,
проверяет CFE в host базе, выполняет Designer syntax check и запускает один
manifest suite из 26 сценариев на обоих targets:

```sh
./scripts/run-container-tests.sh
```

Чтобы открыть те же тестовые формы в реальном клиенте и повторить suite вручную:

```sh
./scripts/run-container-tests.sh --manual
```

Команда переиспользует настроенный image и работающий контейнер, не запускает
release packaging. В manual режиме она сохраняет обе тестовые базы, открывает
CF и CFE формы и печатает локальный VNC/noVNC URL, например
`http://127.0.0.1:6080`. В основной форме видны summary, PASS/FAIL строки,
ожидаемое и фактическое значения и ошибки; кнопку «Повторить автотесты» можно
нажать, чтобы вручную выполнить тот же suite ещё раз.

Native TestClient UI stage выполняется для CF. Сценарии перечислены в
[`tests/ui-scenarios.json`](../tests/ui-scenarios.json), а покрытие экспортных
методов — в [`tests/ui-method-coverage.json`](../tests/ui-method-coverage.json).
В отчёте `ui-cf` таблица показывает метод, ID сценария, прямую/косвенную связь,
статус и наблюдённое значение. 20 из 22 экспортов требуют такого результата;
`ФормаПодготовлена` и `РазложитьСтрокуВМассивПодстрок` отмечены как helpers,
не создающие UI. Список сверяется с экспортами `Module.bsl`. Отсутствующий
сценарий или запуск, заблокированный лицензией, не проходит UI gate.

Отчёты и все логи лежат в уникальном новом каталоге `build/unified-test-run.*`:

- `reports/aggregate/results.json` — canonical aggregate и target результаты;
- `reports/aggregate/report.html` — подробный просмотр;
- `reports/aggregate/junit.xml` — JUnit для систем отчётности;
- `reports/aggregate/report.txt` — краткая текстовая сводка;
- `container-output/` — manifest, логи runtime и сохранённые базы manual режима.

Для упавшего Native TestClient сценария HTML содержит ссылку на PNG снимок окна
клиента, снятый на шаге ошибки. Для успешных сценариев снимки не создаются.

Exit codes unified test command:

- `0` — все обязательные стадии и тесты прошли;
- `1` — проверки выполнились, но suite или обязательная проверка вернула FAIL;
- `2` — orchestration blocked или обязательный отчёт/target отсутствует.

Известные baseline runtime ошибки остаются `FAIL` в отчёте тестов. Release
policy помечает точные совпадения отдельно как `baseline-only`; это не меняет
статус сценария и не скрывает ошибку. На подтверждённом прогоне Linux ARM64
платформы 8.5.1.1529 инфраструктурные стадии прошли, каждый target получил
12 PASS и 14 известных FAIL (0 новых), общий результат — 24 PASS / 28 FAIL
из 52 исполнений, поэтому команда вернула `1`.

## Сборка отдельного расширения `.cfe`

Экспортируйте проект FormEditor из EDT в XML формата Конфигуратора и укажите
путь к `1cv8` или `ibcmd`. Если указан `1cv8`, `ibcmd` должен лежать рядом.

```sh
python3 scripts/build-extension.py \
  --platform "/path/to/1cv8" \
  --source "/path/to/designer-xml-export" \
  --output "build/FormEditor.cfe"
```

Эта команда собирает только расширение `.cfe`. Скрипт подготавливает XML через
`scripts/prepare-extension.py`, создаёт временную файловую базу и проверяет
расширение средствами `ibcmd`. Уже существующий файл результата не
перезаписывается. Для отдельной подготовки XML используйте:

```sh
python3 scripts/prepare-extension.py \
  /path/to/designer-xml-export build/extension-xml
```

## Полный release gate

Запуск релизной сборки и отдельной release policy:

```sh
./scripts/run-container-release.sh
```

Полный список входных данных, этапов, baseline и release decisions описан в
[документе release gate](release-gate.md). Release command проверяет чистоту
исходников и упаковку; owner test runner выше можно запускать на изменённой
рабочей копии без этой release policy.

## Исторические EDT metadata

`legacy/edt-root/` содержит сохранённые исторические root `.settings/` и
`DT-INF/`. Это не входной проект сборки. Старые Vanessa/Windows workflow удалены;
для актуальных проверок используйте единый runner выше.
