# Current Project State

Last updated: 2026-05-20

## Overview

В репозитории два бота:

- Telegram funnel bot в корне репозитория, Python 3.12 + aiogram.
- Discord bot в `services/discord-bot`, Node.js + discord.js.

Telegram-бот запрашивает контакт перед выдачей Discord-ссылки, сохраняет пользователей и события в SQLite, поддерживает admin-команды для постов, рассылок, отложенных публикаций и аналитики по источникам.

## Data Storage

Локально `docker-compose.yml` монтирует папку проекта `./data` в контейнер как `/app/data`:

```yaml
volumes:
  - ./data:/app/data
```

По умолчанию база Telegram-бота находится в `data/bot.sqlite3`. В контейнере при корректной настройке это должен быть путь внутри `/app/data`, например `/app/data/bot.sqlite3`.

По документации Railway у `bootcamp-telegram-bot` должен быть подключен persistent volume `bootcamp-telegram-bot-volume` на `/app/data`, а `DATABASE_PATH` должен указывать на `/app/data/bot.sqlite3`.

## Verified On 2026-05-20

Локальная SQLite-база `data/bot.sqlite3` существует.

Проверенные агрегаты:

- users total: 1
- users with phone/contact: 1
- `start` events: 1
- `start_repeat` events: 1
- `contact_shared` events: 1
- `discord_access_sent` events: 1

Вывод: локально пользователь, который запустил бота и отправил контакт, действительно записался в SQLite.

Стартовый Telegram-flow:

- первый `/start` показывает welcome-сообщение и просит контакт;
- повторный `/start` без сохраненного контакта показывает "с возвращением" и снова просит контакт;
- повторный `/start` с сохраненным контактом не просит номер и сразу выдает Discord-ссылку;
- память о контакте хранится в SQLite, а не только в памяти процесса.
- после сохраненного контакта обычные сообщения и неизвестные команды не получают fallback-ответ, чтобы бот не шумел и не просил номер повторно;
- контакт сохраняется через upsert: если строки пользователя еще нет, она создается сразу с номером.

Рассылки:

- `/broadcast текст` строит payload и отправляет его всем `active` пользователям;
- если Telegram возвращает forbidden, пользователь помечается как `blocked`;
- ядро рассылки покрыто тестами без реальной отправки в Telegram.

Admin posting:

- основной flow отправки запускается через `/post`;
- `/drop_post`, `drop post`, `дроп пост`, `/new_post`, `/newpost` и `new post` остаются старыми алиасами;
- `/post` открывает выбор: пост всем сейчас, рассылка по сегментам или запланировать;
- рассылка по сегментам пока показывает заготовку под будущие теги/сегменты и не отправляет сообщение;
- `/post текст` и `/post` ответом на медиа создают preview и ждут подтверждения;
- после контента мастер спрашивает link-кнопки в формате `Текст кнопки | https://example.com`;
- preview имеет только два действия: `Подтвердить` и `Отменить`; редактирование убрано, чтобы flow не путал админа;
- `/manage` показывает запланированные отправки и позволяет удалить их кнопками;
- мастер отправляет пользователям бота и не требует `TELEGRAM_CHANNEL_ID`.

Admin analytics:

- `/admin` показывает общий размер базы, активных/заблокированных пользователей, новые добавления за 24 часа и 7 дней, контакты, выданные Discord-инвайты и количество start-событий;
- `/analytics` остается алиасом того же отчета;
- источники берутся из deep-link payload `/start`, например `https://t.me/<bot_username>?start=instagram` или `https://t.me/<bot_username>?start=utm_source_instagram`;
- первый найденный источник пользователя сохраняется в `users.source`, прямые заходы отображаются как `direct`.

## Known Limits

- Docker Desktop на момент проверки не отвечал, поэтому живой локальный контейнер не проверялся через `docker compose ps`.
- Railway CLI на момент проверки был не авторизован, поэтому реальный Railway volume не был подтвержден через `railway volume list`.
- Локальная база создана старой версией схемы и не содержит часть новых analytics-колонок до запуска актуального `storage.init()`.

## Health Checks

Telegram tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Последний результат на 2026-05-20: `40 tests OK`.
