# Исторические проектные файлы и Windows runner

Эта папка хранит прежние EDT root metadata и Windows/OneScript workflow. Актуальный
1С EDT-проект и основной код находятся в `../FormEditor/`; текущие проверки и
сборки запускаются через `../scripts/`.

## EDT root metadata

`edt-root/` содержит бывшие корневые `.settings/` и `DT-INF/`. Это отдельные
исторические metadata: root `PROJECT.PMF` указывает Product-Version 1.9.3 и
Runtime-Version 8.3.14, тогда как `FormEditor/DT-INF/PROJECT.PMF` указывает
Runtime-Version 8.3.17. Скрипты сборки и тестов не ссылаются на root metadata.
Они сохранены отдельно, не являются дублем актуального проекта `FormEditor/`.

## Windows/OneScript runner

`vanessa/` содержит прежние `Jenkinsfile`, `run_vanessa.bat`, настройки Runner
и BDD-сценарии. Если Jenkins job использует pipeline script из SCM, настройте её
на файл `legacy/vanessa/Jenkinsfile`: после перемещения в корне репозитория его
больше нет.

В `vanessa/config/v8params.json` каталог сценариев задан как
`legacy/vanessa/features` относительно корня checkout, а отчёты направляются в
`.local/vanessa-output/`. Создайте этот каталог до локального запуска. Запускайте batch-файл из корня checkout, чтобы относительные пути к конфигурации
и каталогу сценариев разрешались корректно. Перед запуском настройте существующую
информационную базу и локальное OneScript/Vanessa Runner окружение.

Jenkins pipeline содержит прежние Windows пути, версии EDT/Ring и платформы 1С.
Перед использованием настройте значения для своего Jenkins agent; исходные
пути оставлены как исторические параметры и не проверялись в текущем окружении.

Текущие проектные entry points — `scripts/run-container-smoke.sh` и
`scripts/run-container-release.sh`. Smoke launcher использует сценарий из
`legacy/vanessa/features/`.
