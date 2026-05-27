import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import content
from app.campaigns import (
    BOOTCAMP_NEXT_STEP_SCHEDULED_AT,
    ensure_bootcamp_next_step_broadcast,
)
from app.keyboards import BOOTCAMP_NEXT_STEP_CALLBACK
from app.storage import EventStorage


class CampaignSchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootcamp_next_step_broadcast_is_scheduled_once(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()

            first_job_id = await ensure_bootcamp_next_step_broadcast(storage)
            second_job_id = await ensure_bootcamp_next_step_broadcast(storage)
            jobs = await storage.list_scheduled_jobs(limit=10)

        self.assertIsNotNone(first_job_id)
        self.assertIsNone(second_job_id)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_type"], "broadcast")
        self.assertEqual(jobs[0]["text"], content.BOOTCAMP_NEXT_STEP_BROADCAST_MESSAGE)
        self.assertTrue(
            jobs[0]["scheduled_at"].startswith("2026-06-06T08:00:00")
        )

        payload = json.loads(jobs[0]["payload"])
        self.assertEqual(payload["text"], content.BOOTCAMP_NEXT_STEP_BROADCAST_MESSAGE)
        self.assertEqual(
            payload["callback_buttons"][0]["callback_data"],
            BOOTCAMP_NEXT_STEP_CALLBACK,
        )

    async def test_scheduled_job_exists_matches_utc_time(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.create_scheduled_job(
                job_type="broadcast",
                text="Test",
                scheduled_at=BOOTCAMP_NEXT_STEP_SCHEDULED_AT,
                created_by=0,
            )

            exists = await storage.scheduled_job_exists(
                job_type="broadcast",
                text="Test",
                scheduled_at=BOOTCAMP_NEXT_STEP_SCHEDULED_AT,
            )

        self.assertTrue(exists)


if __name__ == "__main__":
    unittest.main()
