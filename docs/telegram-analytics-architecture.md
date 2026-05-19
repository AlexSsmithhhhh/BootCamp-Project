# Telegram Bot Analytics Architecture

Цель Telegram-бота - не только выдать Discord-ссылку, а собрать понятную аналитику по воронке BootCamp:

- кто пришел в бота;
- откуда пришел пользователь;
- кто поделился контактом;
- кто получил Discord-доступ;
- кто продолжает взаимодействовать;
- кто заблокировал бота или перестал быть доступен для рассылок;
- какие шаги воронки проседают.

## Принцип

Telegram-бот хранит данные в двух слоях.

1. `users` - текущее состояние пользователя.

   Здесь лежит профиль и последнее известное состояние: Telegram ID, username, имя, телефон, источник, статус подписки, даты первого/последнего взаимодействия, дата получения Discord-инвайта.

2. `events` - append-only журнал событий.

   Каждое действие записывается отдельной строкой: `/start`, повторный `/start`, контакт, отказ от чужого контакта, выдача Discord-ссылки, `/help`, fallback-сообщение, будущие клики и ошибки доставки.

Так мы можем быстро смотреть текущие цифры по `users`, но не теряем историю для аналитики по дням, источникам и шагам.

## Что Уже Трекается

- `start` - первый `/start`.
- `start_repeat` - повторный `/start`.
- `contact_shared` - пользователь отправил свой контакт.
- `contact_rejected_not_own` - пользователь отправил не свой контакт.
- `discord_access_sent` - бот выдал Discord-ссылку.
- `help_requested` - пользователь вызвал `/help`.
- `fallback_message` - пользователь написал что-то вне сценария.
- `delivery_failed` - будущий маркер, когда при рассылке Telegram вернет ошибку доставки.
- `admin_channel_post_sent` - админ опубликовал пост в канал через бота.
- `admin_channel_post_deleted` - админ удалил пост из канала.
- `admin_broadcast_sent` - админ запустил рассылку.
- `scheduled_broadcast_sent` - отложенная рассылка выполнена scheduler worker.

## Подписки И Отписки

В личном Telegram-боте нет отдельного события "user unsubscribed".

Реально доступные сигналы:

- `active` - пользователь запускал бота и бот может считать его доступным.
- `blocked` - определяется, когда бот пытается отправить сообщение, а Telegram возвращает ошибку вроде `bot was blocked by the user`.
- `unsubscribed_at` - фиксируется в момент такой ошибки доставки.

Поэтому для точной аналитики отписок нужна будущая рассылочная/проверочная задача: она отправляет сообщение или сервисное уведомление и помечает недоступных пользователей как `blocked`.

## Источники Трафика

Для источников используем deep links:

```text
https://t.me/<bot_username>?start=utm_source_instagram
https://t.me/<bot_username>?start=utm_source=instagram&campaign=bootcamp_week
```

Бот сохраняет:

- `start_payload` - сырой payload из `/start`;
- `source` - нормализованный источник из `utm_source`, `source`, `src`, `campaign` или сам payload.

## База Данных

Основные поля `users`:

- `telegram_id`
- `username`, `first_name`, `last_name`, `language_code`
- `phone_number`, `contact_received_at`
- `first_seen_at`, `last_seen_at`, `last_interaction_at`
- `start_count`
- `subscription_status`
- `subscribed_at`, `unsubscribed_at`
- `start_payload`, `source`
- `discord_invite_sent_at`
- `last_delivery_error`, `last_delivery_error_at`

Основные поля `events`:

- `telegram_id`
- `event_type`
- `payload`
- `created_at`

## Admin Publications And Broadcasts

Admin-команды доступны только Telegram user IDs из `TELEGRAM_ADMIN_IDS`.

Команды:

- `/post текст` - сразу публикует пост в `TELEGRAM_CHANNEL_ID`.
- `/delete_post message_id` - удаляет пост из `TELEGRAM_CHANNEL_ID`.
- `/broadcast текст` - сразу отправляет сообщение всем пользователям со статусом `active`.
- `/schedule_post YYYY-MM-DD HH:MM | текст` - сохраняет отложенный пост.
- `/schedule_broadcast YYYY-MM-DD HH:MM | текст` - сохраняет отложенную рассылку.
- `/scheduled` - показывает ближайшие задания.
- `/cancel_scheduled id` - отменяет задание, если оно еще не выполнено.

Отложенные задания хранятся в `scheduled_jobs`:

- `job_type`: `channel_post` или `broadcast`;
- `status`: `scheduled`, `processing`, `sent`, `cancelled`, `failed`;
- `text`;
- `target_chat_id`;
- `created_by`;
- `scheduled_at`, `created_at`, `sent_at`;
- `telegram_message_id`;
- `attempts`, `last_error`.

Scheduler worker запускается вместе с Telegram-ботом и проверяет due jobs каждые `SCHEDULER_POLL_INTERVAL_SECONDS` секунд.

Рассылки обновляют аналитику отписок: если Telegram возвращает ошибку, что пользователь заблокировал бота, пользователь помечается как `blocked`, а событие `delivery_failed` записывается в журнал.

## Будущие Отчеты

Минимальный admin dashboard должен показывать:

- всего пользователей;
- активных пользователей;
- заблокировавших бота;
- контактов получено;
- Discord-инвайтов выдано;
- conversion rate: `start -> contact -> discord_access_sent`;
- источники по `source`;
- события по дням;
- пользователи без контакта;
- пользователи, получившие ссылку, но не дошедшие до Discord, когда появится связка с Discord ID.

## Следующие Шаги

1. Добавить admin-only команду `/stats` для короткой сводки.
2. Добавить CSV export по пользователям и событиям.
3. Добавить preview/confirm flow для постов и рассылок перед отправкой.
4. Добавить campaign/deep-link генератор для разных источников трафика.
5. Связать Telegram пользователя с Discord участником через invite tracking или отдельный код подтверждения.
