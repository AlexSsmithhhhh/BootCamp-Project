# Project Structure

Last updated: 2026-05-25

## Коротко

Репозиторий содержит два отдельных бота для BootCamp:

- Telegram funnel bot в корне репозитория: Python 3.12, `aiogram`, SQLite.
- Discord bot в `services/discord-bot`: Node.js 20+, `discord.js`, JSON-хранилище leaderboard.

Оба сервиса деплоятся как отдельные Railway services из одного git-репозитория.

## Дерево проекта

```text
.
├── app/
│   ├── __init__.py
│   ├── admin.py
│   ├── config.py
│   ├── content.py
│   ├── handlers.py
│   ├── keyboards.py
│   ├── main.py
│   ├── scheduler.py
│   └── storage.py
├── data/
│   └── bot.sqlite3
├── docs/
│   ├── README.md
│   ├── bots-and-railway.md
│   ├── current-state.md
│   ├── project-log.md
│   ├── project-structure.md
│   └── telegram-analytics-architecture.md
├── services/
│   └── discord-bot/
│       ├── README.md
│       ├── package-lock.json
│       ├── package.json
│       ├── railway.json
│       ├── scripts/
│       │   ├── inspect-dashboard.js
│       │   ├── inspect-guild.js
│       │   ├── sync-announcement-permissions.js
│       │   └── sync-start-here.js
│       └── src/
│           ├── announcement-permissions.js
│           ├── backfill.js
│           ├── config.js
│           ├── index.js
│           ├── leaderboard.js
│           ├── reaction-roles.js
│           └── storage.js
├── tests/
│   ├── test_admin.py
│   ├── test_admin_post_flow.py
│   ├── test_broadcast.py
│   ├── test_config.py
│   ├── test_handlers.py
│   ├── test_imports.py
│   ├── test_router_order.py
│   └── test_storage.py
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── docker-compose.yml
├── railway.json
└── requirements.txt
```

## Telegram Bot

Назначение: маркетинговая воронка Telegram -> contact gate -> Discord invite, плюс базовая аналитика и админские рассылки.

Основной runtime:

- Python 3.12.
- `aiogram>=3.22,<4`.
- `aiosqlite>=0.20,<1`.
- `python-dotenv>=1.0,<2`.
- SQLite база по умолчанию: `data/bot.sqlite3`.

Ключевые файлы:

- `app/main.py` - точка входа, создает `Bot`, `Dispatcher`, `EventStorage`, запускает polling и scheduler.
- `app/config.py` - загрузка и валидация env-настроек.
- `app/handlers.py` - пользовательский Telegram flow: `/start`, `/help`, `/discord`, `/access`, контакт, fallback.
- `app/admin.py` - admin-only команды, мастер `/post`, рассылки, отложенные задания, media flow, аналитика.
- `app/scheduler.py` - background worker для выполнения due scheduled jobs.
- `app/storage.py` - SQLite schema, миграционные добавления колонок, события, пользователи, drafts, scheduled jobs.
- `app/content.py` - тексты сообщений и подписи кнопок.
- `app/keyboards.py` - contact keyboard и Discord URL inline keyboard.

Пользовательский flow:

- Первый `/start` записывает пользователя и просит поделиться контактом.
- Повторный `/start` без контакта снова просит контакт.
- После сохраненного `contact_received_at` бот больше не просит номер и сразу выдает Discord-ссылку.
- `/discord` и `/access` повторно отправляют Discord invite, если контакт уже сохранен.
- Неизвестные сообщения от пользователей с контактом игнорируются, чтобы бот не шумел.

Admin flow:

- Админы задаются через `TELEGRAM_ADMIN_IDS` и `TELEGRAM_ADMIN_USERNAMES`.
- `/admin_help` показывает список admin-команд.
- `/admin` и `/analytics` показывают аналитику пользователей, контактов, Discord access и источников.
- `/post` запускает мастер поста/рассылки: сейчас всем, сегменты-заготовка, или расписание.
- `/broadcast` отправляет рассылку активным пользователям.
- `/schedule_post` и `/schedule_broadcast` создают отложенные задания.
- `/manage`, `/scheduled`, `/all_post`, `/delete`, `/cancel_scheduled` управляют запланированными отправками.
- Поддерживаются текст, фото, альбомы, видео, PDF/document и optional link-buttons.

Telegram SQLite tables:

- `users` - текущее состояние пользователя, контакт, source, subscription status, timestamps.
- `events` - append-only журнал событий.
- `scheduled_jobs` - отложенные посты и рассылки.
- `admin_media_cache` - временный кеш Telegram media groups.
- `admin_post_drafts` - состояние мастера `/post`.

Telegram env:

- Required: `TELEGRAM_BOT_TOKEN`, `DISCORD_INVITE_URL`.
- Optional: `DATABASE_PATH`, `TELEGRAM_ADMIN_IDS`, `TELEGRAM_ADMIN_USERNAMES`, `TELEGRAM_CHANNEL_ID`, `SCHEDULER_POLL_INTERVAL_SECONDS`.

## Discord Bot

Назначение: Discord leaderboard для BootCamp, reaction roles и служебные slash-команды.

Основной runtime:

- Node.js `>=20`.
- `discord.js^14.19.3`.
- `dotenv^16.4.7`.
- Данные leaderboard по умолчанию: `/app/data/discord-leaderboard.json` на Railway или `data/discord-leaderboard.json` локально.

Ключевые файлы:

- `services/discord-bot/src/index.js` - точка входа, Discord client, intents, slash-команды, event handlers.
- `services/discord-bot/src/announcement-permissions.js` - синхронизация прав анонсов, чтобы Moderator/Модератор и Mentor/Ментор могли писать в канал.
- `services/discord-bot/src/config.js` - env-настройки Discord, leaderboard и reaction roles.
- `services/discord-bot/src/storage.js` - JSON-хранилище leaderboard и начислений.
- `services/discord-bot/src/leaderboard.js` - scoring rules, embeds, dashboard, фильтры рабочих каналов.
- `services/discord-bot/src/reaction-roles.js` - выдача и снятие ролей по реакциям.
- `services/discord-bot/src/backfill.js` - восстановление recent history при старте.
- `services/discord-bot/scripts/inspect-guild.js` - инспекция guild.
- `services/discord-bot/scripts/inspect-dashboard.js` - инспекция dashboard.
- `services/discord-bot/scripts/sync-announcement-permissions.js` - one-off применение прав на запись в анонсах для Moderator/Mentor.
- `services/discord-bot/scripts/sync-start-here.js` - one-off cleanup/repost скрипт для короткого reaction-role prompt в `start-here`.

Slash-команды:

- `/ping` - проверка, что бот работает.
- `/leaderboard` - текущий рейтинг.
- `/my-points` - личные баллы.
- `/award-points` - ручное начисление для Mentor/Support.
- `/leaderboard-dashboard` - создание/обновление dashboard.

Scoring:

- +2 за содержательное сообщение в рабочих чатах.
- +10 за любую реакцию от Mentor/Support, без дневного лимита.
- +25 за каждую stage-сессию от 15 минут, без дневного лимита.
- Mentor/Support не показываются в публичном leaderboard.

Reaction roles:

- В `start-here` реакция ↗️ дает `Forex` + `Trader`.
- В `start-here` реакция 📈 дает `Crypto` + `Trader`.
- `Trader` не снимается при удалении direction reaction.

Discord env:

- Required: `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_GUILD_ID`.
- Leaderboard: `LEADERBOARD_CHANNEL_ID`, `LEADERBOARD_MESSAGE_ID`, `LEADERBOARD_WORKING_CHANNEL_IDS`, `LEADERBOARD_PUBLIC_LIMIT`, `LEADERBOARD_BACKFILL_ON_STARTUP`, `LEADERBOARD_BACKFILL_DAYS`, `LEADERBOARD_BACKFILL_MAX_MESSAGES_PER_CHANNEL`, `LEADERBOARD_MANUAL_AWARD_MAX_POINTS`.
- Announcement permissions: `ANNOUNCEMENT_PERMISSIONS_ENABLED`, `ANNOUNCEMENT_CHANNEL_ID`, `ANNOUNCEMENT_CHANNEL_NAMES`, `ANNOUNCEMENT_WRITER_ROLE_IDS`, `ANNOUNCEMENT_WRITER_ROLE_NAMES`.
- Reaction roles: `REACTION_ROLE_MESSAGE_IDS`, `REACTION_ROLE_CHANNEL_IDS`, `REACTION_ROLE_MEMBER_ROLE_ID`, `REACTION_ROLE_FOREX_ROLE_ID`, `REACTION_ROLE_CRYPTO_ROLE_ID` and role-name overrides.

## Deploy

Railway project: `prolific-joy`, environment: `production`.

Services:

- `bootcamp-telegram-bot`: root directory `/`, start command `python -m app.main`, Dockerfile builder.
- `bootcamp-discord-bot`: root directory `services/discord-bot`, start command `npm start`, Nixpacks builder.

Normal deploy policy:

1. Make local changes.
2. Run checks.
3. Commit and push to GitHub.
4. Redeploy Railway from GitHub source.

Local Railway deploy with `railway up` is documented as emergency fallback only.

## Checks

Current local checks on 2026-05-25:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result: `40 tests OK`.

```powershell
cd services\discord-bot
npm.cmd run check
```

Result: Node syntax check passed for Discord bot source and helper scripts.

Note for Windows PowerShell: `npm run check` can be blocked by ExecutionPolicy because it invokes `npm.ps1`; use `npm.cmd run check`.

## Safety Notes

- Do not print or commit `.env`.
- Do not print Railway raw variable values.
- Do not commit `.railway/`.
- Keep personal data out of docs; use aggregates or masked values.
