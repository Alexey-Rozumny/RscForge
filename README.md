# RscForge

Self-hosted веб-сервис для управления доменами и подсетями и генерации
готовых к импорту `.rsc`-файлов с `ip/firewall/address-list` для MikroTik
RouterOS v7 (PBR / маршрутизация в VPN).

## Возможности

- Источники трёх типов: URL, загруженный файл, ручной ввод.
- Парсинг TXT/CSV/hosts/AdBlock/AdGuard-списков, дедупликация и валидация.
- Автоматическое обновление по расписанию и кнопка «Обновить все».
- Редактирование записей: поиск, фильтры, включение/выключение, удаление.
- Генерация `.rsc` с идемпотентным обновлением address-list.
- Опциональный PBR-блок: mangle, routing table и default route через VPN.
- Basic-аутентификация и отдельный токен для эндпоинта экспорта.
- SQLite и один Docker-контейнер — без внешних зависимостей.

## Быстрый старт

```bash
cp .env.example .env
# отредактируйте .env: задайте RSCFORGE_PASSWORD и RSCFORGE_EXPORT_TOKEN
docker compose up -d --build
```

UI: `http://<host>:8080`

В Docker данные лежат в named volume `rscforge-data`. Если нужен обычный
каталог `./data`, замените в `docker-compose.yml` строку
`- rscforge-data:/data` на `- ./data:/data` и при необходимости выполните
`chown -R 10001:10001 ./data` (контейнер работает не от root).

Без Docker:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn rscforge.main:app --host 0.0.0.0 --port 8000
```

Данные хранятся в `./data` (SQLite + загруженные файлы).

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `RSCFORGE_DATA_DIR` | `data` | Каталог для БД и загрузок |
| `RSCFORGE_DB_PATH` | `<data>/rscforge.db` | Путь к SQLite |
| `RSCFORGE_USERNAME` | `admin` | Логин Basic-аутентификации |
| `RSCFORGE_PASSWORD` | пусто | Пароль; пусто — аутентификация выключена |
| `RSCFORGE_EXPORT_TOKEN` | пусто | Токен для `/export.rsc?token=...` |
| `RSCFORGE_HOST` | `0.0.0.0` | Адрес для `python app.py` |
| `RSCFORGE_PORT` | `8000` | Порт для `python app.py` |
| `RSCFORGE_HTTP_PORT` | `8080` | Порт на хосте (только docker-compose) |
| `RSCFORGE_FETCH_TIMEOUT` | `30` | Таймаут загрузки источника, сек |
| `RSCFORGE_MAX_FETCH_BYTES` | `16777216` | Лимит размера источника |
| `RSCFORGE_MAX_UPLOAD_BYTES` | `16777216` | Лимит размера загружаемого файла |

## Как пользоваться

1. **Источники** — добавьте URL или загрузите файл. Сервис сразу скачает и
   распарсит список. Для каждого источника задаётся интервал обновления.
2. **Записи** — проверьте результат, отключите лишнее, добавьте свои домены,
   IP или CIDR. Ручные записи не удаляются при обновлении источников.
3. **Экспорт** — настройте имя address-list, wildcard-политику и при
   необходимости PBR-правила. Скопируйте готовый `.rsc` или скачайте файл.
4. Настройте MikroTik на периодическую загрузку и импорт файла.

### Обновление списков

При обновлении внешнего источника сервис добавляет новые записи, удаляет
исчезнувшие и сохраняет ваши изменения (включение/выключение и комментарии).
Ручные записи не затрагиваются.

### Wildcard-домены

RouterOS address-list не поддерживает `*.example.com`. По умолчанию такие
записи пропускаются при экспорте. В настройках экспорта можно выбрать
`base-domain` — тогда будет экспортирован `example.com` без wildcard.

## Настройка MikroTik

Пример скрипта и планировщика (RouterOS v7):

```rsc
/system script add name=rscforge-update source={
    /tool fetch url="http://192.168.88.10:8080/export.rsc?token=CHANGE_ME" dst-path=rscforge.rsc
    /import file-name=rscforge.rsc
}

/system scheduler add name=rscforge interval=1h on-event=rscforge-update
```

Если включена Basic-аутентификация, добавьте в `fetch`:

```rsc
/tool fetch url="http://192.168.88.10:8080/export.rsc" \
    user=admin password="CHANGE_ME" dst-path=rscforge.rsc
```

### PBR-блок

Если включить PBR, в `.rsc` добавляются:

- правила `mangle` для mark-connection и mark-routing;
- routing table с флагом `fib`;
- default route `0.0.0.0/0` через VPN-шлюз.

Для правила mark-connection нужен address-list локальной сети (по умолчанию
`local-networks`). Создайте его заранее или укажите другое имя в настройках:

```rsc
/ip/firewall/address-list add list=local-networks address=192.168.88.0/24
```

Имена списка, таблицы, меток и шлюз настраиваются на вкладке «Экспорт».
Значения по умолчанию: `vpn-filter`, `vpn-filter-con`, `new-con`,
`local-networks`.

## Формат `.rsc`

```rsc
# RscForge export
# generated: 2026-11-21T12:00:00+00:00
# list: vpn-filter
# entries: 2 (domains: 1, ip/cidr: 1)

/ip/firewall/address-list
remove [find list="vpn-filter" comment~"^rscforge:"]
add list="vpn-filter" address=example.com comment="rscforge:src=Blocklist"
add list="vpn-filter" address=10.0.0.0/8 comment="rscforge:LAN"
```

Обновление идемпотентно: удаляются только записи с комментарием `rscforge:`,
поэтому ручные записи в том же address-list не затрагиваются.

## API

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/healthz` | Healthcheck (без auth) |
| `GET/POST` | `/api/sources` | Список / создание URL-источника |
| `POST` | `/api/sources/upload` | Загрузка файла |
| `PATCH/DELETE` | `/api/sources/{id}` | Изменение / удаление |
| `POST` | `/api/sources/{id}/refresh` | Обновить один источник |
| `POST` | `/api/sources/refresh-all` | Обновить все источники |
| `GET/POST` | `/api/entries` | Список / ручное добавление |
| `GET` | `/api/entries/stats` | Сводная статистика |
| `PATCH/DELETE` | `/api/entries/{id}` | Изменение / удаление |
| `POST` | `/api/entries/bulk` | Массовые операции |
| `GET` | `/api/export/preview` | Предпросмотр `.rsc` |
| `GET` | `/api/export/download` | Скачивание `.rsc` из UI |
| `GET` | `/export.rsc` | Эндпоинт для MikroTik (токен или Basic auth) |
| `GET/PATCH` | `/api/settings` | Настройки экспорта |

## Разработка

```bash
pip install -r requirements-dev.txt
pytest
```

Структура:

```
rscforge/
  main.py          # FastAPI, lifespan, роутеры
  config.py        # переменные окружения
  db.py            # SQLite-схема
  repositories.py  # доступ к данным
  parsers.py       # парсинг и нормализация
  rsc.py           # генератор .rsc
  services.py      # загрузка и обновление источников
  scheduler.py     # периодическое обновление
  auth.py          # Basic auth + export token
  routers/         # HTTP API
  templates/       # Jinja2 UI
  static/          # CSS/JS
tests/
```

## Ограничения

- Один address-list и один набор настроек экспорта (без мультисписков).
- Нет многопользовательского режима и ролей.
- Домены резолвит сам MikroTik; сервис не проверяет доступность DNS.
- Wildcard-домены не поддерживаются RouterOS address-list.
- Записи внешних источников синхронизируются с источником; ручные — нет.

## Безопасность

- Обязательно задайте `RSCFORGE_PASSWORD`, если сервис доступен другим
  устройствам в сети.
- Для MikroTik используйте `RSCFORGE_EXPORT_TOKEN`, чтобы не передавать
  пароль администратора в скриптах.
- Не публикуйте сервис в интернет напрямую; при необходимости — reverse proxy
  с HTTPS.
- Источники скачиваются сервером, поэтому не добавляйте URL от недоверенных
  пользователей (риск SSRF).
