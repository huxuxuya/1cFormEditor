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

На GitHub события `pull_request` и `push` запускают hosted workflow
`Portable checks`. Его зелёный статус означает только прохождение Python unit
tests и `bash -n`; EDT, 1С, лицензированный контейнер, CF/CFE и release gate в
GitHub runner не запускаются. В сводке job видны точный checked-out SHA,
версия из `Configuration.mdo` и границы проверки. PR head SHA показан отдельно,
поскольку GitHub обычно проверяет merge revision.

## Единый runner CF/CFE

Одна команда экспортирует текущий EDT-проект, собирает и проверяет CF/CFE,
проверяет CFE в host базе, выполняет Designer syntax check и запускает один
manifest suite из 30 сценариев на обоих targets:

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
статус и наблюдённое значение. 20 из 23 экспортов требуют UI проверки;
`ФормаПодготовлена`, `НовыйКонтекстЭлемента` и `РазложитьСтрокуВМассивПодстрок`
проверяются runtime-сценариями, поскольку не создают UI. Список сверяется с
экспортами `Module.bsl`. Отсутствующий
сценарий или запуск, заблокированный лицензией, не проходит UI gate.

Для навигации по истории запусков откройте `build/index.html`. Он отдельно
показывает последнюю завершённую проверку и более новую незавершённую попытку,
а также группирует test-run и release-run. Runner обновляет индекс автоматически;
пересобрать его по существующим локальным данным без Docker можно командой
`python3 scripts/build_index.py`.
На macOS открыть страницу можно командой `open build/index.html`.

Подробные отчёты и логи каждого тестового прогона лежат в уникальном каталоге
`build/unified-test-run.YYYY-MM-DD_HH-MM-SS.*`:

- `reports/aggregate/results.json` — canonical aggregate и target результаты;
- `reports/aggregate/report.html` — подробный просмотр;
- `reports/aggregate/junit.xml` — JUnit для систем отчётности;
- `reports/aggregate/report.txt` — краткая текстовая сводка;
- `reports/aggregate/summary.md` — версия конфигурации, SHA/state исходников,
  платформа, итоги CF/CFE/UI, baseline-разделение и хеши CF/CFE;
- `container-output/` — manifest, логи runtime и сохранённые базы manual режима.

Для release run такая же `summary.md` лежит рядом с aggregate в
`build/release-run.*/release/reports/aggregate/`; `release/manifest.json`
содержит решение gate и артефактные SHA256. Без явно переданного tag summary
показывает тестовое evidence без привязки к релизу. Проверить существующий tag
на точное совпадение с текущим clean build можно так:

```sh
git describe --tags --exact-match
./scripts/run-container-release.sh --tag "$(git describe --tags --exact-match)"
```

Команда использует локальный Git tag с точным именем (в репозитории tags без
префикса `v`); tag должен указывать на текущий commit и быть доступен в
`refs/tags` на этой машине. Сводка напишет «Validated for release» только если tag резолвится в SHA сборки,
точно совпадает с версией конфигурации, manifest разрешает release, а SHA256 и
размеры CF/CFE совпадают. При любом расхождении она показывает причины и
классифицирует результат как candidate/test evidence. Команда ничего не
публикует. Для ручного оформления релиза владелец прикладывает согласованные
`summary.md`, HTML/JUnit/JSON отчёты, manifest и опубликованные файлы только
после проверки tag verdict; CI и локальный runner сами не загружают release
assets.

Для упавшего Native TestClient сценария HTML содержит ссылку на PNG снимок окна
клиента, снятый на шаге ошибки. Для успешных сценариев снимки не создаются.

Exit codes unified test command:

- `0` — все обязательные стадии и тесты прошли;
- `1` — проверки выполнились, но suite или обязательная проверка вернула FAIL;
- `2` — orchestration blocked или обязательный отчёт/target отсутствует.

Известные baseline runtime ошибки остаются `FAIL` в отчёте тестов. Release
policy помечает точные совпадения отдельно как `baseline-only`; это не меняет
статус сценария и не скрывает ошибку. На подтверждённом прогоне Linux ARM64
платформы 8.5.1.1529 инфраструктурные стадии прошли, UI suite — 14/14, а
каждый runtime target получил 26 PASS и 4 FAIL: три известные baseline ошибки и
отдельный FAIL явного выбора реквизита. Общий результат — 52 PASS / 8 FAIL из 60
исполнений; baseline-сопоставление не меняет фактический статус сценария.

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
