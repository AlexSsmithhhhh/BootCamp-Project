from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.campaigns import ensure_bootcamp_next_step_broadcast
from app.config import ConfigurationError, Settings
from app.handlers import router
from app.scheduler import run_scheduler
from app.storage import EventStorage


async def run_bot() -> None:
    settings = Settings.from_env()
    storage = EventStorage(settings.database_path)
    await storage.init()
    await ensure_bootcamp_next_step_broadcast(storage)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    scheduler_task = asyncio.create_task(run_scheduler(bot, storage, settings))
    try:
        await dispatcher.start_polling(
            bot,
            settings=settings,
            storage=storage,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_bot())
    except ConfigurationError as exc:
        logging.critical("Configuration error: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
