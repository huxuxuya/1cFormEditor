[![Последний релиз](https://img.shields.io/github/v/release/huxuxuya/1cFormEditor?label=release)](https://github.com/huxuxuya/1cFormEditor/releases)

# FormEditor

Модуль 1С для программного добавления реквизитов, полей, групп, таблиц и команд
управляемых форм.

## Короткий пример

```bsl
КонтекстФормы = РедакторФорм.НовыйКонтекстЭлемента(ЭтотОбъект);
КонтекстФормы.Свойства.Вставить("Вид", ВидГруппыФормы.ОбычнаяГруппа);
ГруппаШапка = РедакторФорм.НоваяГруппаФормы(КонтекстФормы, "ГруппаШапка");
```

Подробные примеры и описание методов находятся в [руководстве по API](docs/api.md).

## Структура проекта

- Исходники 1С находятся в `FormEditor/src/`.
- Python-проверки лежат в `tests/`, прежние BDD-сценарии — в `legacy/vanessa/features/`;
  команды сборки и запуска —
  в `scripts/` и `docker/`.
- `legacy/` хранит прежние EDT/Windows runner файлы; `.local/` — локальные данные,
  исключённые из Git.
- Полная карта каталогов и правила размещения новых файлов — в
  [карте репозитория](docs/repository-layout.md).

## Навигация

- [Установка, использование и API](docs/api.md)
- [Разработка и проверки](docs/development.md)
- [Полная процедура release gate](docs/release-gate.md)
- [Docker smoke-тест](docker/1c-smoke/README.md)
- [Карта репозитория](docs/repository-layout.md)
- [История изменений](CHANGELOG.md)

## Быстрые команды

Python unit tests:

```sh
python3 -m unittest discover -s tests -v
```

Проверка Docker smoke-тулчейна:

```sh
./scripts/run-container-smoke.sh --check-toolchain
```

Для сборки отдельного .cfe и полного release gate сначала ознакомьтесь с
[инструкцией разработки](docs/development.md).
