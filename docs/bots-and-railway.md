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

Обязательные переменные:

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_INVITE_URL`
- `DATABASE_PATH`, обычно `data/bot.sqlite3`

Локальная проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Деплой:

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd up --service "bootcamp-telegram-bot" --environment "production" --detach --json --message "Deploy Telegram bot"
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

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd up ".\services\discord-bot" --path-as-root --service "bootcamp-discord-bot" --environment "production" --detach --json --message "Deploy Discord bot"
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
- обновляет dashboard в канале `leaderboard` каждые 5 минут.

Текущая Railway-настройка:

- `LEADERBOARD_CHANNEL_ID` = канал `leaderboard`.
- `LEADERBOARD_MESSAGE_ID` = fixed Discord message id for the public dashboard. When this is set, the bot edits only that message and does not auto-create another dashboard if the message cannot be fetched or edited.
- `LEADERBOARD_WORKING_CHANNEL_IDS` = `fx-chat`, `crypto-chat`.
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

3. Деплоить Telegram только в `bootcamp-telegram-bot`.

4. Деплоить Discord только в `bootcamp-discord-bot` и только с `--path-as-root`.

5. После деплоя смотреть `railway.cmd logs --latest --lines 100`.
