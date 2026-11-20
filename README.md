[![Последний релиз](https://img.shields.io/github/v/release/huxuxuya/1cFormEditor?label=release)](https://github.com/huxuxuya/1cFormEditor/releases)

# FormEditor

[![Portable checks (Python and shell only)](https://github.com/huxuxuya/1cFormEditor/actions/workflows/portable-checks.yml/badge.svg?branch=master)](https://github.com/huxuxuya/1cFormEditor/actions/workflows/portable-checks.yml)

Библиотека 1С для программного добавления реквизитов, полей, групп, таблиц и
команд управляемых форм.

```bsl
КонтекстФормы = РедакторФорм.НовыйКонтекстЭлемента(ЭтотОбъект);
КонтекстФормы.Свойства.Вставить("Вид", ВидГруппыФормы.ОбычнаяГруппа);
ГруппаШапка = РедакторФорм.НоваяГруппаФормы(КонтекстФормы, "ГруппаШапка");
```

Подробные примеры и описание методов — в [руководстве по API](docs/api.md).

## Навигация

- [Разработка и единый запуск проверок](docs/development.md)
- [Release gate и baseline](docs/release-gate.md)
- [Карта репозитория](docs/repository-layout.md)
- [История изменений](CHANGELOG.md)

Исходники EDT находятся в `FormEditor/`, тесты и manifest сценариев — в
`tests/`, owner команды — в `scripts/`, а контейнерные файлы release gate — в
`docker/1c-release/`. Исторические EDT root metadata сохранены в
`legacy/edt-root/`. Локальные настройки и результаты проверок в `.local/` и
`build/` исключены из Git.

## Быстрый запуск

```sh
python3 -m unittest discover -s tests -v
./scripts/run-container-tests.sh
./scripts/run-container-tests.sh --manual
```

Обычный запуск сохраняет JSON, HTML, JUnit XML, текстовый отчёт и логи в новый
каталог `build/unified-test-run.YYYY-MM-DD_HH-MM-SS.*`. Ручной режим открывает те же тестовые формы
в активном локальном UI. Требования и трактовка статусов описаны в
[инструкции разработки](docs/development.md).

После первого запуска откройте `build/index.html`: там отдельно собраны история
тестов, последние отчёты, снимки ошибок и пакеты release-run. Оба runner обновляют
индекс автоматически; чтобы пересобрать его по уже имеющимся каталогам без Docker,
выполните `python3 scripts/build_index.py`, затем `open build/index.html`.
