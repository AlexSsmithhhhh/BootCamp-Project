# bootcamp-discord-bot

Локальный Discord-сервис для Railway service `bootcamp-discord-bot`.

Этот код восстановлен в репозитории как рабочая база BootCamp Week leaderboard: он логинится в Discord, держит сервис online, считает активность и регистрирует guild slash-команды:

- `/ping`
- `/leaderboard`
- `/my-points`
- `/leaderboard-dashboard`

## Scoring

- +2 балла за содержательное сообщение в рабочих чатах, максимум 30 баллов в день.
- +10 баллов за реакцию ✅ или 🔥 от роли Mentor/Support, максимум 50 баллов в день.
- +25 баллов за участие в stage от 15 минут, один раз в день.

Рабочие Railway-переменные:

- `LEADERBOARD_CHANNEL_ID` - канал dashboard. Сейчас это `leaderboard`.
- `LEADERBOARD_MESSAGE_ID` - fixed dashboard message. If it is set, the bot edits only this message and never creates a replacement automatically.
- `LEADERBOARD_WORKING_CHANNEL_IDS` - рабочие чаты. Сейчас это `fx-chat` и `crypto-chat`.

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
