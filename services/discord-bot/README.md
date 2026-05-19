# bootcamp-discord-bot

Локальный Discord-сервис для Railway service `bootcamp-discord-bot`.

Этот код восстановлен в репозитории как рабочая база BootCamp Week leaderboard: он логинится в Discord, держит сервис online, считает активность и регистрирует guild slash-команды:

- `/ping`
- `/leaderboard`
- `/my-points`
- `/award-points`
- `/leaderboard-dashboard`

## Scoring

- +2 балла за содержательное сообщение в рабочих чатах, максимум 30 баллов в день.
- +10 баллов за реакцию ✅ или 🔥 от роли Mentor/Support, максимум 50 баллов в день.
- +25 баллов за участие в stage от 15 минут, один раз в день.
- Роль `Mentor`, `ментор`, `Support`, `саппорт` или `наставник` может вручную начислять баллы командой `/award-points`.
- Пользователи с mentor/support-ролью не отображаются в публичном leaderboard.
- Публичный dashboard показывает топ-5 и кнопку `Мои баллы`, которая отвечает пользователю приватно даже в закрытом для сообщений канале.

Рабочие Railway-переменные:

- `LEADERBOARD_CHANNEL_ID` - канал dashboard. Сейчас это `leaderboard`.
- `LEADERBOARD_MESSAGE_ID` - fixed dashboard message. If it is set, the bot edits only this message and never creates a replacement automatically.
- `LEADERBOARD_WORKING_CHANNEL_IDS` - рабочие чаты. Сейчас это `fx-chat` и `crypto-chat`.
- `LEADERBOARD_PUBLIC_LIMIT` - сколько участников показывать в публичном dashboard, по умолчанию `5`.
- `LEADERBOARD_BACKFILL_ON_STARTUP` - включить восстановление истории рабочих каналов при старте, по умолчанию `true`.
- `LEADERBOARD_BACKFILL_DAYS` - сколько дней истории читать при восстановлении, по умолчанию `14`.
- `LEADERBOARD_BACKFILL_MAX_MESSAGES_PER_CHANNEL` - лимит сообщений на канал для восстановления, по умолчанию `1000`.
- `LEADERBOARD_MANUAL_AWARD_MAX_POINTS` - максимум баллов за одно ручное начисление, по умолчанию `100`.

Данные хранятся в `/app/data/discord-leaderboard.json` на Railway volume.

## Local check

```powershell
npm install
npm run check
```

## Deploy

```powershell
$env:RAILWAY_TOKEN = "<project-token>"
railway.cmd up ".\services\discord-bot" --path-as-root --service "bootcamp-discord-bot" --environment "production" --detach --json --message "Deploy Discord bot"
```
