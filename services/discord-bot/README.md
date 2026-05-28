# bootcamp-discord-bot

Локальный Discord-сервис для Railway service `bootcamp-discord-bot`.

Этот код восстановлен в репозитории как рабочая база BootCamp Week leaderboard: он логинится в Discord, держит сервис online, считает активность и регистрирует guild slash-команды:

- `/ping`
- `/leaderboard`
- `/my-points`
- `/award-points`
- `/leaderboard-dashboard`

## Scoring

- +2 балла за содержательное сообщение в рабочих чатах, без дневного лимита (антиспам-фильтр остается).
- +10 баллов за реакцию от роли Mentor/Support в рабочем чате, без дневного лимита.
- +25 баллов за каждую stage-сессию от 15 минут, без дневного лимита.
- Роль `Mentor`, `ментор`, `Support`, `саппорт` или `наставник` может вручную начислять баллы командой `/award-points`.
- Пользователи с mentor/support-ролью не отображаются в публичном leaderboard.
- Публичный dashboard показывает топ-5 и кнопку `Мои баллы`, которая отвечает пользователю приватно даже в закрытом для сообщений канале.

Рабочие Railway-переменные:

- `LEADERBOARD_CHANNEL_ID` - канал dashboard. Сейчас это `leaderboard`.
- `LEADERBOARD_MESSAGE_ID` - fixed dashboard message. If it is set, the bot edits only this message and never creates a replacement automatically.
- `LEADERBOARD_WORKING_CHANNEL_IDS` - рабочий чат. Сейчас это ID канала `work-chat`.
- `LEADERBOARD_PUBLIC_LIMIT` - сколько участников показывать в публичном dashboard, по умолчанию `5`.
- `LEADERBOARD_BACKFILL_ON_STARTUP` - включить восстановление истории рабочих каналов при старте, по умолчанию `true`.
- `LEADERBOARD_BACKFILL_DAYS` - сколько дней истории читать при восстановлении, по умолчанию `14`.
- `LEADERBOARD_BACKFILL_MAX_MESSAGES_PER_CHANNEL` - лимит сообщений на канал для восстановления, по умолчанию `1000`.
- `LEADERBOARD_MANUAL_AWARD_MAX_POINTS` - максимум баллов за одно ручное начисление, по умолчанию `100`.

Данные хранятся в `/app/data/discord-leaderboard.json` на Railway volume.

## Announcement Permissions

At startup the bot syncs announcement-channel permissions so moderators and mentors can write there.

Defaults:

- channel is found by `ANNOUNCEMENT_CHANNEL_ID` if set, otherwise by common names: `announcements`, `announcement`, `news`, `анонсы`, `анонс`, `объявления`;
- writer roles are found by `ANNOUNCEMENT_WRITER_ROLE_IDS` if set, otherwise by names like `Moderator`, `Mod`, `модератор`, `Mentor`, `ментор`, `наставник`.

Optional Railway variables:

- `ANNOUNCEMENT_PERMISSIONS_ENABLED` - set to `false` to disable this sync, default `true`.
- `ANNOUNCEMENT_CHANNEL_ID` / `ANNOUNCEMENTS_CHANNEL_ID` / `DISCORD_ANNOUNCEMENT_CHANNEL_ID` - target announcements channel. Recommended for production.
- `ANNOUNCEMENT_CHANNEL_NAMES` - comma-separated fallback channel names.
- `ANNOUNCEMENT_WRITER_ROLE_IDS` - comma-separated role IDs allowed to write. Recommended if role names change.
- `ANNOUNCEMENT_WRITER_ROLE_NAMES` - comma-separated fallback role names.

The bot role must have `Manage Channels`, and its role must be above the roles it edits in Discord role hierarchy.

To apply the same permissions once via Discord API:

```powershell
npm run sync:announcements
```

Optional variable for a dry run:

- `ANNOUNCEMENT_DRY_RUN=true` - print target channel and roles without changing permissions.

## Reaction Roles

In `start-here`, direction reactions grant access roles:

- ↗️ -> `Forex` + `Trader`
- 📈 -> `Crypto` + `Trader`

`Trader` is the base server access role. It is always added when a user chooses Forex or Crypto, and it is not removed if the user later removes a direction reaction. If a user selects both directions, the bot keeps `Trader` and grants both `Forex` and `Crypto`.

Optional Railway variables:

- `REACTION_ROLE_MESSAGE_IDS` - specific welcome message IDs for reaction roles (recommended).
- `REACTION_ROLE_CHANNEL_IDS` - channel IDs for reaction roles. If empty, the bot uses a `start-here` channel by name.
- `REACTION_ROLE_MEMBER_ROLE_ID` / `REACTION_ROLE_MEMBER_ROLE_NAMES` - base access role, default `Member`.
- `REACTION_ROLE_FOREX_ROLE_ID` / `REACTION_ROLE_FOREX_ROLE_NAMES` / `REACTION_ROLE_FOREX_EMOJIS` - Forex direction, default role `Forex`, emoji 🗺.
- `REACTION_ROLE_CRYPTO_ROLE_ID` / `REACTION_ROLE_CRYPTO_ROLE_NAMES` / `REACTION_ROLE_CRYPTO_EMOJIS` - Crypto direction, default role `Crypto`, emoji 📈.

To clean up and repost the `start-here` prompt below Smith's message:

```powershell
railway.cmd run --service "bootcamp-discord-bot" --environment "production" -- npm run sync:start-here
```

Optional variables:

- `START_HERE_CHANNEL_ID` - exact channel/thread ID. Recommended.
- `START_HERE_ANCHOR_MESSAGE_ID` - exact Smith message ID. Recommended if there are many recent messages.
- `START_HERE_DRY_RUN=true` - preview what would change without deleting or posting.

The script deletes only bot-authored messages that contain the old welcome/start-here prompt, then posts the short direction-selection embed with the `🔒 Доступ к серверу откроется 1 июня 🚀` note and adds ↗️/📈 reactions. If `REACTION_ROLE_MESSAGE_IDS` is set, update it to the new message ID printed by the script, or remove that env variable so reaction roles work by channel.

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
