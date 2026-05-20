# BootCamp-Project

Документы проекта начинаются с `docs/README.md`.
Документация по двум Railway-сервисам лежит в `docs/bots-and-railway.md`.
Архитектура аналитики Telegram-бота лежит в `docs/telegram-analytics-architecture.md`.
В проекте сейчас два бота: Telegram-бот в корне репозитория и Discord-бот в `services/discord-bot`.

Технический каркас Telegram-бота для маркетинговой воронки мероприятия.
Сейчас бот специально минимальный: финальные тексты, кнопки и сценарии будут добавлены позже.

## Что уже есть

- Python bot на `aiogram`.
- Docker Compose запуск через polling.
- Конфигурация через `.env`.
- Запрос номера телефона перед выдачей Discord-ссылки.
- SQLite-учет базовых событий: `/start`, повторный `/start`, отправка контакта, выдача Discord-ссылки.
- `/admin` аналитика по пользователям, контактам, новым пользователям и UTM-like источникам из deep links.
- Admin-команды Telegram и мастер `/post` для отправки постов/рассылок пользователям бота с preview, ссылочными кнопками, подтверждением, планированием, текстом, фото, альбомами, видео и PDF.

## Быстрый старт

1. Создай `.env` по примеру:

   ```bash
   cp .env.example .env
   ```

2. Заполни переменные:

   ```env
   TELEGRAM_BOT_TOKEN=token-from-botfather
   DISCORD_INVITE_URL=https://discord.gg/your-invite
   DATABASE_PATH=data/bot.sqlite3
   ```

3. Собери и запусти:

   ```bash
   docker compose up --build -d
   ```

4. Посмотри логи:

   ```bash
   docker compose logs -f bot
   ```

## Тесты

```bash
docker compose run --rm bot python -m unittest discover -s tests
```

## Где менять тексты

Основные placeholder-тексты и названия кнопок лежат в `app/content.py`.
Когда будут готовы финальные материалы мероприятия, их можно заменить там без изменения логики бота.
