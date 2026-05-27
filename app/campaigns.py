from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app import content
from app.keyboards import BOOTCAMP_NEXT_STEP_CALLBACK
from app.storage import EventStorage


logger = logging.getLogger(__name__)

BOOTCAMP_NEXT_STEP_SCHEDULED_AT = datetime(
    2026,
    6,
    6,
    11,
    0,
    tzinfo=timezone(timedelta(hours=3)),
)
BOOTCAMP_NEXT_STEP_CREATED_BY = 0


async def ensure_bootcamp_next_step_broadcast(storage: EventStorage) -> Optional[int]:
    if await storage.scheduled_job_exists(
        job_type="broadcast",
        text=content.BOOTCAMP_NEXT_STEP_BROADCAST_MESSAGE,
        scheduled_at=BOOTCAMP_NEXT_STEP_SCHEDULED_AT,
    ):
        logger.info(
            "Bootcamp next step broadcast already scheduled for %s",
            BOOTCAMP_NEXT_STEP_SCHEDULED_AT.isoformat(),
        )
        return None

    job_id = await storage.create_scheduled_job(
        job_type="broadcast",
        text=content.BOOTCAMP_NEXT_STEP_BROADCAST_MESSAGE,
        payload={
            "kind": "text",
            "text": content.BOOTCAMP_NEXT_STEP_BROADCAST_MESSAGE,
            "callback_buttons": [
                {
                    "text": content.BOOTCAMP_NEXT_STEP_BUTTON_TEXT,
                    "callback_data": BOOTCAMP_NEXT_STEP_CALLBACK,
                }
            ],
        },
        scheduled_at=BOOTCAMP_NEXT_STEP_SCHEDULED_AT,
        created_by=BOOTCAMP_NEXT_STEP_CREATED_BY,
    )
    logger.info(
        "Scheduled Bootcamp next step broadcast job_id=%s scheduled_at=%s",
        job_id,
        BOOTCAMP_NEXT_STEP_SCHEDULED_AT.isoformat(),
    )
    return job_id
