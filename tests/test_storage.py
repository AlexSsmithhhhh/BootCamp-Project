import json
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import connect
from tempfile import TemporaryDirectory

from aiogram.types import Contact, User

from app.quiz import CATEGORY_LABELS, SYSTEM_GAP, tag_for_result
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
            self.assertFalse(await storage.user_has_contact(user.id))
            await storage.save_contact(user, contact)
            self.assertTrue(await storage.user_has_contact(user.id))
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

    async def test_tracks_sources_for_admin_analytics(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            await storage.record_start(
                User(id=1002, is_bot=False, first_name="Dana"),
                "utm_source_instagram",
            )
            await storage.record_start(
                User(id=1003, is_bot=False, first_name="Mira"),
                "source=facebook&campaign=bootcamp",
            )
            await storage.record_start(User(id=1004, is_bot=False, first_name="No UTM"))

            sources = await storage.analytics_sources()

        counts = {row["source"]: row["users_total"] for row in sources}
        self.assertEqual(counts["instagram"], 1)
        self.assertEqual(counts["facebook"], 1)
        self.assertEqual(counts["direct"], 1)

    async def test_preserves_first_known_source_on_repeat_start(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1006, is_bot=False, first_name="Nika")
            await storage.record_start(user, "utm_source_instagram")
            await storage.record_start(user, "utm_source_youtube")

            with closing(connect(database_path)) as db:
                source = db.execute(
                    "SELECT source FROM users WHERE telegram_id = ?",
                    (user.id,),
                ).fetchone()[0]

        self.assertEqual(source, "instagram")

    async def test_save_contact_upserts_user_without_prior_start(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1005, is_bot=False, first_name="Mira", username="mira")
            contact = Contact(
                phone_number="+380671112233",
                first_name="Mira",
                user_id=user.id,
            )

            await storage.save_contact(user, contact)

            with closing(connect(database_path)) as db:
                phone_number, start_count, status = db.execute(
                    """
                    SELECT phone_number, start_count, subscription_status
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (user.id,),
                ).fetchone()

        self.assertEqual(phone_number, "+380671112233")
        self.assertEqual(start_count, 0)
        self.assertEqual(status, "active")

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
                payload={"kind": "text", "text": "Draft post"},
            )

            draft = await storage.admin_post_draft(1001)
            await storage.clear_admin_post_draft(1001)
            deleted_draft = await storage.admin_post_draft(1001)

        self.assertIsNotNone(draft)
        self.assertEqual(draft["mode"], "scheduled")
        self.assertEqual(draft["status"], "awaiting_content")
        self.assertEqual(draft["media_group_id"], "album-1")
        self.assertEqual(json.loads(draft["payload"])["text"], "Draft post")
        self.assertIsNone(deleted_draft)

    async def test_admin_post_draft_payload_column_is_migrated(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            with closing(connect(database_path)) as db:
                db.execute(
                    """
                    CREATE TABLE admin_post_drafts (
                        admin_id INTEGER PRIMARY KEY,
                        mode TEXT NOT NULL,
                        status TEXT NOT NULL,
                        scheduled_at TEXT,
                        media_group_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                db.commit()

            storage = EventStorage(database_path)
            await storage.init()
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="now",
                status="awaiting_confirm",
                payload={"kind": "text", "text": "Migrated draft"},
            )

            draft = await storage.admin_post_draft(1001)
            with closing(connect(database_path)) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(admin_post_drafts)")}

        self.assertIn("payload", columns)
        self.assertEqual(json.loads(draft["payload"])["text"], "Migrated draft")

    async def test_quiz_attempt_lifecycle(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1007, is_bot=False, first_name="Quiz")
            attempt = await storage.start_quiz_attempt(user)
            updated_attempt = await storage.record_quiz_answer(
                user=user,
                attempt_id=attempt["id"],
                question_index=0,
                answer_key="A",
                category=SYSTEM_GAP,
                category_label=CATEGORY_LABELS[SYSTEM_GAP],
            )
            completed_attempt = await storage.complete_quiz_attempt(
                user=user,
                attempt_id=attempt["id"],
                result_key=SYSTEM_GAP,
                result_tag=tag_for_result(SYSTEM_GAP),
                scores={SYSTEM_GAP: 1},
            )
            latest_completed = await storage.latest_completed_quiz_attempt(user.id)
            with closing(connect(database_path)) as db:
                quiz_result_key, quiz_result_tag, quiz_scores = db.execute(
                    """
                    SELECT quiz_result_key, quiz_result_tag, quiz_scores
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (user.id,),
                ).fetchone()
                stored_tag, tag_source, tag_metadata = db.execute(
                    """
                    SELECT tag, source, metadata
                    FROM user_tags
                    WHERE telegram_id = ?
                    """,
                    (user.id,),
                ).fetchone()

        self.assertEqual(attempt["status"], "in_progress")
        self.assertEqual(updated_attempt["current_question_index"], 1)
        self.assertEqual(updated_attempt["answers"][0]["answer_key"], "A")
        self.assertEqual(updated_attempt["scores"][SYSTEM_GAP], 1)
        self.assertEqual(completed_attempt["status"], "completed")
        self.assertEqual(latest_completed["result_key"], SYSTEM_GAP)
        self.assertEqual(quiz_result_key, SYSTEM_GAP)
        self.assertEqual(quiz_result_tag, "system_gap")
        self.assertEqual(json.loads(quiz_scores), {SYSTEM_GAP: 1})
        self.assertEqual(stored_tag, "system_gap")
        self.assertEqual(tag_source, "quiz_result")
        self.assertEqual(json.loads(tag_metadata)["result_key"], SYSTEM_GAP)

    async def test_user_has_contact_when_event_exists_without_user_contact_fields(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1003, is_bot=False, first_name="Sam", username="sam")
            await storage.record_start(user)

            with closing(connect(database_path)) as db:
                db.execute(
                    """
                    INSERT INTO events (telegram_id, event_type, payload, created_at)
                    VALUES (?, 'contact_shared', ?, ?)
                    """,
                    (user.id, "{}", datetime.now(timezone.utc).isoformat()),
                )
                db.commit()

            self.assertTrue(await storage.user_has_contact(user.id))

    async def test_contact_prompt_cooldown(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1004, is_bot=False, first_name="Nika", username="nika")
            await storage.record_start(user)

            self.assertTrue(await storage.should_prompt_contact(user.id, cooldown_seconds=3600))
            await storage.mark_contact_prompted(user)
            self.assertFalse(await storage.should_prompt_contact(user.id, cooldown_seconds=3600))


if __name__ == "__main__":
    unittest.main()
