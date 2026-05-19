# Bootcamp Bots: рабочая документация

Актуальная архитектура проекта: один репозиторий, два отдельных Railway-сервиса.

## Сервисы

| Назначение | Railway service | Локальный путь | Runtime | Start command |
| --- | --- | --- | --- | --- |
| Telegram funnel bot | `bootcamp-telegram-bot` | корень репозитория | Python 3.12 + aiogram | `python -m app.main` |
| Discord bot | `bootcamp-discord-bot` | `services/discord-bot` | Node.js + discord.js | `npm start` |

Важно: не деплоить корень репозитория в `bootcamp-discord-bot`. Для Discord всегда использовать `--path-as-root services/discord-bot`.

## Railway

Project: `prolific-joy`

Environment: `production`

Сервисы:

- `bootcamp-telegram-bot` - отдельный сервис для Telegram-бота.
- `bootcamp-discord-bot` - отдельный сервис для Discord-бота.

## Git-first deploy workflow

GitHub is the source of truth for production deploys. Do not deploy regular changes with local `railway up`.

Normal flow:

1. Make code/docs changes locally.
2. Run checks:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests
   cd services\discord-bot
   npm run check
   ```

3. Commit and push:

   ```powershell
   git status --short --branch
   git add -- <changed-files>
   git commit -m "<clear message>"
   git push origin main
   ```

4. Deploy from the configured GitHub source in Railway:

   ```powershell
   $env:RAILWAY_TOKEN = "<project-token>"
   railway.cmd deployment redeploy --service "bootcamp-telegram-bot" --environment "production" --from-source --yes --json
   railway.cmd deployment redeploy --service "bootcamp-discord-bot" --environment "production" --from-source --yes --json
   ```

Railway service source settings should stay connected to `AlexSsmithhhhh/BootCamp-Project`:

- `bootcamp-telegram-bot`: root directory `/`, start command `python -m app.main`.
- `bootcamp-discord-bot`: root directory `services/discord-bot`, start command `npm start`.

Use local `railway up` only as an emergency fallback, and document why it was needed.

Проверка статуса:

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd service status --service "bootcamp-telegram-bot" --environment "production" --json
railway.cmd service status --service "bootcamp-discord-bot" --environment "production" --json
```

Логи:

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd logs --service "bootcamp-telegram-bot" --environment "production" --latest --lines 100
railway.cmd logs --service "bootcamp-discord-bot" --environment "production" --latest --lines 100
```

## Telegram-бот

Код находится в корне репозитория:

- `app/main.py` - точка входа.
- `app/config.py` - конфигурация из env.
- `app/handlers.py` - Telegram-сценарии.
- `app/storage.py` - SQLite-учет событий.
- `app/content.py` - тексты и placeholder-контент.

Подробная архитектура аналитики Telegram-бота лежит в `docs/telegram-analytics-architecture.md`.

Обязательные переменные:

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_INVITE_URL`
- `DATABASE_PATH`, обычно `data/bot.sqlite3`

Дополнительные переменные для admin-команд Telegram:

- `TELEGRAM_ADMIN_IDS` - comma-separated Telegram user IDs администраторов, которым доступны публикации и рассылки.
- `TELEGRAM_ADMIN_USERNAMES` - optional comma-separated Telegram usernames без `@`; удобно, когда числовой user ID еще неизвестен.
- `TELEGRAM_CHANNEL_ID` - канал для публикаций, например `@channel_name` или `-100...`.
- `SCHEDULER_POLL_INTERVAL_SECONDS` - частота проверки отложенных заданий, по умолчанию `30`.

Admin-команды Telegram:

- `/admin_help` - список команд.
- `/new_post`, `/newpost` или `new post` - мастер создания поста: выбрать "сейчас" или "запланировать", затем отправить контент.
- `/all_post` или `all post` - список запланированных публикаций.
- `/delete ID` или `delete ID` - отменить запланированную публикацию.
- `/analytics` или `analytics` - краткая аналитика Telegram-бота.
- `/post текст` - сразу опубликовать пост в `TELEGRAM_CHANNEL_ID`.
- `/post` ответом на фото/альбом/видео/PDF - опубликовать это медиа в `TELEGRAM_CHANNEL_ID`.
- Фото/видео/PDF с caption `/post текст` - сразу опубликовать медиа с подписью, без отдельной команды.
- `/delete_post message_id` - удалить пост из канала.
- `/broadcast текст` - сразу отправить рассылку всем активным пользователям.
- `/broadcast` ответом на фото/альбом/видео/PDF - отправить медиа всем активным пользователям.
- Фото/видео/PDF с caption `/broadcast текст` - сразу отправить медиа-рассылку.
- `/schedule_post YYYY-MM-DD HH:MM | текст` - запланировать пост в канал.
- `/schedule_post YYYY-MM-DD HH:MM` ответом на медиа - запланировать медиа-пост.
- `/schedule_broadcast YYYY-MM-DD HH:MM | текст` - запланировать рассылку.
- `/schedule_broadcast YYYY-MM-DD HH:MM` ответом на медиа - запланировать медиа-рассылку.
- `/scheduled` - ближайшие активные задания.
- `/cancel_scheduled id` - отменить задание.

Media workflow:

1. Админ отправляет боту в личку фото, Telegram-альбом из нескольких фото, небольшое видео или PDF/document.
2. Админ отвечает на это сообщение командой `/post`, `/broadcast`, `/schedule_post YYYY-MM-DD HH:MM` или `/schedule_broadcast YYYY-MM-DD HH:MM`.
3. Текст после команды становится caption. Для отложенных медиа caption пишется после `|`, например `/schedule_post 2026-05-20 14:00 | Caption`.
4. Быстрый вариант для немедленной отправки: caption самого медиа начинается с `/post текст` или `/broadcast текст`.
5. Альбомы кешируются в SQLite table `admin_media_cache`, а готовый payload для отложенной отправки хранится в `scheduled_jobs.payload`.

New post wizard:

1. Admin writes `/new_post`, `/newpost` or `new post`.
2. Bot asks whether to publish now or schedule.
3. For schedule, admin sends date/time in `YYYY-MM-DD HH:MM`.
4. Bot asks for content; admin sends text, photo, photo album, video, or PDF/document. Caption becomes post text for media.
5. `/all_post` shows scheduled jobs and `/delete ID` cancels a scheduled job.

Contact gate:

- A user shares phone contact only once.
- After `contact_received_at` is saved in SQLite, `/start` and fallback messages no longer ask for the phone number again.
- Known users get the Discord link directly.

Время в командах планирования вводится в timezone `Europe/Kiev`. Задания хранятся в SQLite table `scheduled_jobs` и выполняются фоновым worker внутри Telegram-сервиса.

Локальная проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Деплой:

Основной способ - push в GitHub и redeploy from source в Railway:

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd deployment redeploy --service "bootcamp-telegram-bot" --environment "production" --from-source --yes --json
```

Примечание: у `bootcamp-telegram-bot` сейчас нет отдельного Railway volume, потому что текущий project token не дает создавать/прикреплять volumes. Бот работает, но SQLite-файл внутри контейнера не является долговечным между redeploy. Нужно добавить volume `/app/data` через Railway dashboard или account-level token.

## Discord-бот

Код находится в `services/discord-bot`.

Файлы:

- `services/discord-bot/package.json` - Node-пакет и команды.
- `services/discord-bot/src/index.js` - точка входа.
- `services/discord-bot/railway.json` - Railway start command.

Обязательные переменные:

- `DISCORD_TOKEN`
- `DISCORD_CLIENT_ID`
- `DISCORD_GUILD_ID`

Дополнительные переменные, которые уже есть на Railway:

- `DATABASE_PATH`
- `DISCORD_INVITE_URL`
- `NODE_ENV`

Локальная проверка синтаксиса:

```powershell
cd services\discord-bot
npm install
npm run check
```

Деплой:

Основной способ - push в GitHub и redeploy from source в Railway:

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd deployment redeploy --service "bootcamp-discord-bot" --environment "production" --from-source --yes --json
```

## Что восстановлено по Discord

Старый Discord-код не находился в текущем git-репозитории и не скачивается из Railway через project token. По Railway-логам старый сервис запускался как `npm start` -> `node src/index.js` и логинился как `Cryptomannn BOT Manager`.

В `services/discord-bot` восстановлен рабочий Discord-бот для BootCamp Week leaderboard:

- логинится по текущим Railway-переменным;
- регистрирует guild slash-команды `ping`, `leaderboard`, `my-points`, `award-points`, `leaderboard-dashboard`;
- считает +2 за содержательное сообщение в рабочих чатах, до 30 баллов в день;
- считает +10 за ✅ или 🔥 от Mentor/Support, до 50 баллов в день;
- считает +25 за stage от 15 минут, один раз в день;
- дает Mentor/Support вручную начислять баллы через `/award-points`;
- скрывает пользователей с mentor/support-ролью из публичного leaderboard;
- хранит данные в `/app/data/discord-leaderboard.json` на Railway volume;
- обновляет компактный dashboard в канале `leaderboard` каждые 5 минут: топ-5 и кнопка `Мои баллы`, без правил начисления и наград;
- кнопка `Мои баллы` отвечает приватно через Discord interaction, поэтому работает даже если участник не может отправлять сообщения в `leaderboard`.

Текущая Railway-настройка:

- `LEADERBOARD_CHANNEL_ID` = канал `leaderboard`.
- `LEADERBOARD_MESSAGE_ID` = fixed Discord message id for the public dashboard. When this is set, the bot edits only that message and does not auto-create another dashboard if the message cannot be fetched or edited.
- `LEADERBOARD_WORKING_CHANNEL_IDS` = `fx-chat`, `crypto-chat`.
- `LEADERBOARD_PUBLIC_LIMIT` = `5` by default.
- `LEADERBOARD_BACKFILL_ON_STARTUP` = `true` by default; restores recent message/reaction history from working channels after deploy without double-counting already awarded messages.
- `LEADERBOARD_BACKFILL_DAYS` = `14` by default.
- `LEADERBOARD_BACKFILL_MAX_MESSAGES_PER_CHANNEL` = `1000` by default.
- `LEADERBOARD_MANUAL_AWARD_MAX_POINTS` = `100` by default.
- роли Mentor/Support определяются по названиям ролей `Mentor`, `ментор`, `Support`, `саппорт`, `наставник`.

## Безопасность

- `.env` не коммитится.
- `.railway/` не коммитится.
- Токены не выводить в README, issue, PR и логи команд.
- Для команд `railway variable list --json` и `--kv` помнить: Railway печатает raw values.

## Быстрый runbook

1. Проверить локальные тесты Telegram:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests
   ```

2. Проверить Discord:

   ```powershell
   cd services\discord-bot
   npm run check
   ```

3. Сделать commit и push в `main`.

4. Деплоить Railway только from GitHub source:

   ```powershell
   railway.cmd deployment redeploy --service "bootcamp-telegram-bot" --environment "production" --from-source --yes --json
   railway.cmd deployment redeploy --service "bootcamp-discord-bot" --environment "production" --from-source --yes --json
   ```

5. После деплоя смотреть `railway.cmd logs --latest --lines 100`.
