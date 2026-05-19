from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.admin import execute_due_job
from app.config import Settings
from app.storage import EventStorage


logger = logging.getLogger(__name__)


async def run_scheduler(bot: Bot, storage: EventStorage, settings: Settings) -> None:
    while True:
        try:
            jobs = await storage.due_scheduled_jobs()
            for job in jobs:
                await execute_due_job(bot, storage, job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to process scheduled Telegram jobs.")

        await asyncio.sleep(settings.scheduler_poll_interval_seconds)
