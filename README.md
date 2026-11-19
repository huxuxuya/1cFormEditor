[![Последний релиз](https://img.shields.io/github/v/release/huxuxuya/1cFormEditor?label=release)](https://github.com/huxuxuya/1cFormEditor/releases)

# FormEditor

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
каталог `build/unified-test-run.*`. Ручной режим открывает те же тестовые формы
в активном локальном UI. Требования и трактовка статусов описаны в
[инструкции разработки](docs/development.md).
