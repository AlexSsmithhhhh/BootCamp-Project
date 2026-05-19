import json
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import connect
from tempfile import TemporaryDirectory

from aiogram.types import Contact, User

from app.storage import EventStorage


class EventStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_starts_and_contact(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1001, is_bot=False, first_name="Alex", username="alex")
            contact = Contact(
                phone_number="+380501112233",
                first_name="Alex",
                user_id=user.id,
            )

            self.assertTrue(await storage.record_start(user))
            self.assertFalse(await storage.record_start(user))
            await storage.save_contact(user, contact)
            await storage.mark_discord_access_sent(user)
            overview = await storage.analytics_overview()

            with closing(connect(database_path)) as db:
                start_count, phone_number, status, invite_sent_at = db.execute(
                    """
                    SELECT start_count, phone_number, subscription_status, discord_invite_sent_at
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (user.id,),
                ).fetchone()
                event_types = [
                    row[0]
                    for row in db.execute(
                        "SELECT event_type FROM events ORDER BY id"
                    ).fetchall()
                ]

        self.assertEqual(start_count, 2)
        self.assertEqual(phone_number, "+380501112233")
        self.assertEqual(status, "active")
        self.assertIsNotNone(invite_sent_at)
        self.assertEqual(overview["users_total"], 1)
        self.assertEqual(overview["contacts_shared"], 1)
        self.assertEqual(overview["discord_invites_sent"], 1)
        self.assertEqual(
            event_types,
            ["start", "start_repeat", "contact_shared", "discord_access_sent"],
        )

    async def test_records_start_payload_source(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1002, is_bot=False, first_name="Dana", username="dana")
            await storage.record_start(user, "utm_source=instagram&campaign=bootcamp")

            with closing(connect(database_path)) as db:
                start_payload, source = db.execute(
                    """
                    SELECT start_payload, source
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (user.id,),
                ).fetchone()

        self.assertEqual(start_payload, "utm_source=instagram&campaign=bootcamp")
        self.assertEqual(source, "instagram")

    async def test_scheduled_jobs_lifecycle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            job_id = await storage.create_scheduled_job(
                job_type="channel_post",
                text="Hello channel",
                payload={"kind": "photo", "file_id": "photo-file", "caption": "Hello"},
                target_chat_id="-100123",
                scheduled_at=datetime.now(timezone.utc),
                created_by=1001,
            )

            jobs = await storage.due_scheduled_jobs()
            self.assertEqual(jobs[0]["id"], job_id)
            self.assertEqual(json.loads(jobs[0]["payload"])["kind"], "photo")
            self.assertTrue(await storage.mark_job_processing(job_id))
            self.assertFalse(await storage.mark_job_processing(job_id))
            await storage.mark_job_sent(job_id, telegram_message_id=55)

            with closing(connect(database_path)) as db:
                status, message_id = db.execute(
                    """
                    SELECT status, telegram_message_id
                    FROM scheduled_jobs
                    WHERE id = ?
                    """,
                    (job_id,),
                ).fetchone()

        self.assertEqual(status, "sent")
        self.assertEqual(message_id, 55)

    async def test_admin_media_cache_collects_album(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            await storage.save_admin_media(
                admin_id=1001,
                media_group_id="album-1",
                message_id=10,
                media_type="photo",
                file_id="photo-1",
                caption="Album caption",
            )
            await storage.save_admin_media(
                admin_id=1001,
                media_group_id="album-1",
                message_id=11,
                media_type="photo",
                file_id="photo-2",
            )

            media = await storage.admin_media_group(
                admin_id=1001,
                media_group_id="album-1",
            )

        self.assertEqual([item["file_id"] for item in media], ["photo-1", "photo-2"])
        self.assertEqual(media[0]["caption"], "Album caption")

    async def test_admin_post_draft_lifecycle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            scheduled_at = datetime.now(timezone.utc)
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="scheduled",
                status="awaiting_content",
                scheduled_at=scheduled_at,
                media_group_id="album-1",
            )

            draft = await storage.admin_post_draft(1001)
            await storage.clear_admin_post_draft(1001)
            deleted_draft = await storage.admin_post_draft(1001)

        self.assertIsNotNone(draft)
        self.assertEqual(draft["mode"], "scheduled")
        self.assertEqual(draft["status"], "awaiting_content")
        self.assertEqual(draft["media_group_id"], "album-1")
        self.assertIsNone(deleted_draft)


if __name__ == "__main__":
    unittest.main()
