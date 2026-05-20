import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.admin import (
    build_message_payload,
    confirm_admin_post_draft,
    execute_direct_media_action,
    start_admin_post_preview_from_payload,
    start_admin_post_wizard,
)
from app.config import Settings
from app.storage import EventStorage


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str | int, str]] = []

    async def send_message(self, chat_id: str | int, text: str):
        self.sent_messages.append((chat_id, text))
        return SimpleNamespace(message_id=len(self.sent_messages))


class FakeResponder:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(
            id=1001,
            username="admin",
            first_name="Admin",
            last_name=None,
            language_code="ru",
        )
        self.reply_to_message = None
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


def settings(channel_id: str | None = "@channel") -> Settings:
    return Settings(
        telegram_bot_token="token",
        discord_invite_url="https://discord.gg/test",
        database_path=Path("data/bot.sqlite3"),
        telegram_admin_ids=frozenset({1001}),
        telegram_admin_usernames=frozenset(),
        telegram_channel_id=channel_id,
        scheduler_poll_interval_seconds=30,
    )


class AdminPostFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_post_payload_starts_wizard_path(self) -> None:
        message = FakeResponder()

        payload = await build_message_payload(message, storage=None, text=None)

        self.assertIsNone(payload)

    async def test_start_wizard_without_channel_shows_setup_guide(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            message = FakeResponder()

            await start_admin_post_wizard(message, storage, settings(channel_id=None))

            draft = await storage.admin_post_draft(1001)

        self.assertIsNone(draft)
        self.assertIn("TELEGRAM_CHANNEL_ID", message.answers[-1])

    async def test_post_payload_creates_preview_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            message = FakeResponder()
            bot = FakeBot()

            await start_admin_post_preview_from_payload(
                message=message,
                storage=storage,
                settings=settings(),
                payload={"kind": "text", "text": "Needs review"},
            )

            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNotNone(draft)
        self.assertEqual(draft["status"], "awaiting_confirm")
        self.assertIn("Needs review", draft["payload"])
        self.assertIn("Needs review", message.answers[-1])

    async def test_media_caption_post_creates_preview_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            message = FakeResponder()
            bot = FakeBot()

            await execute_direct_media_action(
                message=message,
                bot=bot,
                storage=storage,
                settings=settings(),
                action="post",
                payload={"kind": "text", "text": "Caption command"},
            )

            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNotNone(draft)
        self.assertEqual(draft["status"], "awaiting_confirm")
        self.assertIn("Caption command", draft["payload"])

    async def test_confirm_now_publishes_payload_and_clears_draft(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="now",
                status="awaiting_confirm",
                payload={"kind": "text", "text": "Hello channel"},
            )
            bot = FakeBot()
            responder = FakeResponder()

            await confirm_admin_post_draft(
                responder=responder,
                bot=bot,
                storage=storage,
                settings=settings(),
                admin_id=1001,
            )

            draft = await storage.admin_post_draft(1001)
            with closing(sqlite3.connect(Path(tmp_dir) / "bot.sqlite3")) as db:
                event_type = db.execute(
                    "SELECT event_type FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]

        self.assertEqual(bot.sent_messages, [("@channel", "Hello channel")])
        self.assertIsNone(draft)
        self.assertEqual(event_type, "admin_channel_post_sent")
        self.assertIn("Пост опубликован", responder.answers[-1])

    async def test_confirm_scheduled_creates_job_and_clears_draft(self) -> None:
        scheduled_at = datetime(2026, 5, 20, 14, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="scheduled",
                status="awaiting_confirm",
                scheduled_at=scheduled_at,
                payload={"kind": "text", "text": "Scheduled post"},
            )
            bot = FakeBot()
            responder = FakeResponder()

            await confirm_admin_post_draft(
                responder=responder,
                bot=bot,
                storage=storage,
                settings=settings(),
                admin_id=1001,
            )

            jobs = await storage.list_scheduled_jobs()
            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNone(draft)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_type"], "channel_post")
        self.assertEqual(jobs[0]["target_chat_id"], "@channel")
        self.assertIn("Пост запланирован", responder.answers[-1])

    async def test_confirm_without_channel_shows_setup_guide(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="now",
                status="awaiting_confirm",
                payload={"kind": "text", "text": "Hello"},
            )
            bot = FakeBot()
            responder = FakeResponder()

            await confirm_admin_post_draft(
                responder=responder,
                bot=bot,
                storage=storage,
                settings=settings(channel_id=None),
                admin_id=1001,
            )

            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNotNone(draft)
        self.assertIn("TELEGRAM_CHANNEL_ID", responder.answers[-1])


if __name__ == "__main__":
    unittest.main()
