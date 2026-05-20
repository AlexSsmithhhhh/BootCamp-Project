# Project Log

Журнал коротких записей по проекту: что проверили, что решили, какие ограничения остались. Новые записи добавляем сверху.

## 2026-05-20 - `/admin` analytics и UTM-like источники

Запрос: сделать команду `/admin`, которая показывает, сколько людей добавилось и из каких сегментов/UTM-источников они пришли.

Что изменено:

- добавлена команда `/admin`; `/analytics` остался алиасом того же отчета;
- отчет показывает users total/active/blocked, новых за 24 часа и 7 дней, контакты, Discord-инвайты, start-события и event log total;
- добавлена группировка по `users.source`: users, contacts и contact conversion по каждому источнику;
- deep-link payload из `/start` поддерживает простые сегменты `instagram`, prefix-форматы `utm_source_instagram`, `campaign_bootcamp`, `segment_partner`, а также key-value payload если он дошел до бота;
- первый найденный source пользователя сохраняется как acquisition source и не перезаписывается повторными `/start` с другим payload.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `39 tests OK`.

## 2026-05-20 - `/manage` и link-кнопки под постами

Запрос: управлять запланированными отправками из бота и добавлять кнопки-ссылки под посты.

Что изменено:

- добавлена команда `/manage`: показывает активные scheduled jobs и кнопки `Удалить ID`;
- delete-кнопка отменяет scheduled job через `cancel_scheduled_job()`;
- `/post` после контента спрашивает optional link-кнопки;
- формат кнопок: `Текст кнопки | https://example.com`, одна кнопка на строку, до 100 кнопок;
- payload теперь может содержать `buttons`, а `send_payload_to_chat()` прикрепляет inline keyboard к text/photo/video/document;
- для photo album кнопки уходят отдельным сообщением `Ссылки к посту:`, потому что Telegram не поддерживает inline keyboard прямо на media group.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `36 tests OK`.

## 2026-05-20 - `/post` wizard для отправки пользователям бота

Запрос: сделать `/post` понятным диалогом в личке админа, без обязательного Telegram-канала.

Что изменено:

- `/post` открывает меню `Пост всем сейчас`, `Рассылка по сегментам`, `Запланировать`;
- `Пост всем сейчас` отправляет всем активным пользователям бота после preview/confirm;
- `Рассылка по сегментам` зарезервирована под будущий выбор тегов/сегментов и сейчас не отправляет сообщение;
- `Запланировать` спрашивает дату и время, затем контент, preview и подтверждение;
- `/post текст`, reply `/post` на медиа и media caption `/post текст` больше не требуют `TELEGRAM_CHANNEL_ID` и тоже идут через preview;
- confirm now вызывает `send_broadcast()`, confirm scheduled создает `scheduled_jobs` с `job_type="broadcast"`;
- старые алиасы `/drop_post`, `drop post`, `дроп пост`, `/new_post`, `/newpost`, `new post` оставлены.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `33 tests OK`.

## 2026-05-20 - Admin posting wizard `/drop_post`

Запрос: сделать понятный flow публикации прямо в Telegram-боте для администратора.

Что изменено:

- добавлен основной wizard `/drop_post` с алиасами `drop post` и `дроп пост`;
- `/new_post`, `/newpost` и `new post` оставлены как старые алиасы;
- `/post текст` больше не публикует сразу: он создает preview и ждет подтверждения, а `/post` без текста открывает wizard;
- wizard проверяет `TELEGRAM_CHANNEL_ID` и показывает setup-инструкцию, если канал не задан;
- после получения текста/медиа бот сохраняет payload в `admin_post_drafts.payload`;
- добавлен preview с кнопками `Опубликовать`/`Запланировать`, `Редактировать`, `Отменить`;
- confirm `now` публикует пост в канал, confirm `scheduled` создает `scheduled_jobs`;
- добавлена SQLite migration для `admin_post_drafts.payload`.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `33 tests OK`.

## 2026-05-20 - Fix: `/start` не отвечал админу

Симптом: после production deploy команда `/start` доходила до бота, в Railway logs update помечался как handled, но пользователь не получал ответ.

Причина:

- пользователь находится в `TELEGRAM_ADMIN_IDS`;
- admin catch-all handler был зарегистрирован до публичных handler-ов `/start`, `/discord` и contact;
- из-за этого `/start` админа перехватывался admin draft handler-ом и тихо завершался, если активного draft не было.

Что изменено:

- публичные handler-ы `/start`, `/help`, `/discord` и contact теперь регистрируются до admin-команд;
- admin-команды остаются выше общего fallback;
- общий fallback остается последним;
- добавлен тест порядка router-ов.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `24 tests OK`.

Production deploy:

- commit: `cc11cb8`
- service: `bootcamp-telegram-bot`
- deployment id: `bc18e3ff-294d-4a7f-a51f-1f5c69a60c3c`
- status: `SUCCESS`
- runtime log: polling запущен для `@bootcampweek_bot`

## 2026-05-20 - Production deploy в правильный Railway service

Проверили Railway project `prolific-joy` / environment `production`.

Правильный Telegram-сервис:

- service: `bootcamp-telegram-bot`
- service id: `a59aecdc-43f4-4f04-b6cc-e99a75498d95`
- volume: `bootcamp-telegram-bot-volume`
- mount path: `/app/data`
- `DATABASE_PATH`: `/app/data/bot.sqlite3`

Важная находка:

- `bootcamp-telegram-bot` имеет `source: null`, то есть не привязан к GitHub source.
- Обычный redeploy переиспользует старый CLI archive.
- Для доставки нового кода нужен `railway up` в конкретный service id.

Что сделано:

```powershell
railway.cmd up --project "55d55619-92ba-4faf-b5e9-82c0e901b65b" --environment "production" --service "a59aecdc-43f4-4f04-b6cc-e99a75498d95" --detach --json --message "Fix Telegram contact memory flow"
```

Результат:

- deployment id: `84b00af3-d339-4f15-93e1-00b4a834b4e4`
- status: `SUCCESS`
- start command: `python -m app.main`
- runtime log: polling запущен для `@bootcampweek_bot` (`BootCamp Open Week`)

## 2026-05-20 - Fix: бот повторно просил номер после сохраненного контакта

Симптом со скрина: пользователь отправил контакт, получил Discord-ссылку, затем написал произвольную команду/текст, а бот снова попросил поделиться номером.

Что изменено:

- `save_contact()` теперь делает SQLite upsert: создает пользователя с контактом, если строки еще нет, или обновляет существующую строку.
- `handle_fallback()` теперь молчит для пользователей с сохраненным контактом. Неизвестные сообщения после открытия доступа больше не получают ответ "поделись номером".
- `/discord` и `/start` остаются явными командами, на которые бот может отвечать.
- Добавлен тест, что `save_contact()` сохраняет контакт даже без предварительного `/start`.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `23 tests OK`.

Важно для production:

Скрин показывает старые тексты бота, значит живой Telegram-бот еще работает на старом коде или старом деплое. После merge/push нужен redeploy/restart активного сервиса и проверка, что нет второго процесса со старым bot token.

## 2026-05-20 - Welcome-flow, память контакта и проверка рассылок

Запрос: сделать welcome-сценарий для первого запуска и повторного `/start`, не запрашивать номер повторно, если пользователь уже оставлял контакт, и проверить команды рассылки.

Что сделано:

- Первый `/start` показывает welcome-сообщение и просит контакт.
- Повторный `/start` без контакта показывает отдельное сообщение для возвращающегося пользователя.
- Повторный `/start` с уже сохраненным контактом убирает клавиатуру контакта и сразу выдает Discord-ссылку.
- Логика выбора start-сообщения вынесена в `start_message_for_state()`.
- Добавлены тесты на start-flow.
- Добавлены тесты на ядро рассылки `send_broadcast()`: успешная отправка активным пользователям и пометка blocked-пользователя при `TelegramForbiddenError`.

Проверка:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Результат: `22 tests OK`.

## 2026-05-20 - Проверка сохранения контактов Telegram

Запрос: проверить, есть ли volume и записываются ли пользователи, которые запустили Telegram-бота и оставили контакт.

Что проверено:

- В `docker-compose.yml` есть bind mount `./data:/app/data`.
- Настройка `DATABASE_PATH` по умолчанию ведет в `data/bot.sqlite3`.
- Код `/start` вызывает `EventStorage.record_start()`.
- Отправка контакта обрабатывается в `handle_contact()` и сохраняется через `EventStorage.save_contact()`.
- В локальной базе `data/bot.sqlite3` есть один пользователь с сохраненным контактом.
- В таблице `events` есть события `start`, `start_repeat`, `contact_shared`, `discord_access_sent`.
- Тесты проекта прошли: `17 tests OK`.

Вывод:

Локально сохранение пользователей и контактов работает. Данные лежат в SQLite в папке `data`, которая при локальном Docker Compose монтируется в контейнер.

Ограничения:

- Docker daemon не был запущен, поэтому контейнер не проверялся как live-process.
- Railway CLI не был авторизован, поэтому удаленный Railway volume не подтвержден командой CLI.

Рекомендация:

После авторизации Railway CLI проверить production volume и переменную `DATABASE_PATH`:

```powershell
railway.cmd volume list --json
railway.cmd run --service "bootcamp-telegram-bot" --environment "production" -- powershell -NoProfile -Command "$env:DATABASE_PATH"
```
