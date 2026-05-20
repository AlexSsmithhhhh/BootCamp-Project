import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from aiogram.types import User

from app.admin import (
    build_message_payload,
    confirm_admin_post_draft,
    execute_direct_media_action,
    admin_post_preview_keyboard,
    new_post_keyboard,
    parse_link_buttons_input,
    send_manage_jobs,
    send_payload_to_chat,
    start_admin_post_preview_from_payload,
    start_admin_post_wizard,
)
from app.config import Settings
from app.storage import EventStorage


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str | int, str]] = []
        self.message_kwargs: list[dict] = []

    async def send_message(self, chat_id: str | int, text: str, **kwargs):
        self.sent_messages.append((chat_id, text))
        self.message_kwargs.append(kwargs)
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
        self.answer_kwargs: list[dict] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)
        self.answer_kwargs.append(kwargs)


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

    async def test_post_starts_wizard_without_channel_setup_block(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            message = FakeResponder()

            await start_admin_post_wizard(message, storage, settings(channel_id=None))

            draft = await storage.admin_post_draft(1001)
            reply_markup = message.answer_kwargs[-1]["reply_markup"]
            callbacks = [
                button.callback_data
                for row in reply_markup.inline_keyboard
                for button in row
            ]

        self.assertIsNotNone(draft)
        self.assertEqual(draft["mode"], "choose")
        self.assertEqual(draft["status"], "choosing")
        self.assertNotIn("TELEGRAM_CHANNEL_ID", message.answers[-1])
        self.assertIn("admin_post_now", callbacks)
        self.assertIn("admin_post_broadcast", callbacks)
        self.assertIn("admin_post_schedule", callbacks)

    def test_post_keyboard_distinguishes_all_users_and_segments(self) -> None:
        keyboard = new_post_keyboard()

        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("Пост всем сейчас", labels)
        self.assertIn("Рассылка по сегментам", labels)
        self.assertIn("Запланировать", labels)

    def test_preview_keyboard_has_only_confirm_and_cancel(self) -> None:
        keyboard = admin_post_preview_keyboard("broadcast_scheduled")

        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertEqual(labels, ["Запланировать", "Отменить"])
        self.assertNotIn("Редактировать", labels)

    def test_parses_link_buttons_input(self) -> None:
        parsed = parse_link_buttons_input(
            "Discord | https://discord.gg/test\n"
            "Site https://example.com"
        )

        self.assertIsNone(parsed["error"])
        self.assertEqual(
            parsed["buttons"],
            [
                {"text": "Discord", "url": "https://discord.gg/test"},
                {"text": "Site", "url": "https://example.com"},
            ],
        )

    async def test_post_payload_creates_preview_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            message = FakeResponder()
            bot = FakeBot()

            await start_admin_post_preview_from_payload(
                message=message,
                storage=storage,
                settings=settings(channel_id=None),
                payload={"kind": "text", "text": "Needs review"},
            )

            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNotNone(draft)
        self.assertEqual(draft["status"], "awaiting_buttons")
        self.assertIn("Needs review", draft["payload"])
        self.assertIn("Кнопки", message.answers[-1])

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
                settings=settings(channel_id=None),
                action="post",
                payload={"kind": "text", "text": "Caption command"},
            )

            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNotNone(draft)
        self.assertEqual(draft["status"], "awaiting_buttons")
        self.assertIn("Caption command", draft["payload"])

    async def test_confirm_now_broadcasts_payload_and_clears_draft(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.record_start(User(id=2001, is_bot=False, first_name="Alex"))
            await storage.record_start(User(id=2002, is_bot=False, first_name="Dana"))
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="broadcast_now",
                status="awaiting_confirm",
                payload={"kind": "text", "text": "Hello bot users"},
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
            with closing(sqlite3.connect(Path(tmp_dir) / "bot.sqlite3")) as db:
                event_type = db.execute(
                    "SELECT event_type FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]

        self.assertEqual(bot.sent_messages, [(2001, "Hello bot users"), (2002, "Hello bot users")])
        self.assertIsNone(draft)
        self.assertEqual(event_type, "admin_broadcast_sent")
        self.assertIn("2", responder.answers[-1])

    async def test_confirm_scheduled_creates_broadcast_job_and_clears_draft(self) -> None:
        scheduled_at = datetime(2026, 5, 20, 14, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.save_admin_post_draft(
                admin_id=1001,
                mode="broadcast_scheduled",
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
                settings=settings(channel_id=None),
                admin_id=1001,
            )

            jobs = await storage.list_scheduled_jobs()
            draft = await storage.admin_post_draft(1001)

        self.assertEqual(bot.sent_messages, [])
        self.assertIsNone(draft)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_type"], "broadcast")
        self.assertIsNone(jobs[0]["target_chat_id"])
        self.assertIn("ID", responder.answers[-1])

    async def test_send_payload_attaches_link_buttons(self) -> None:
        bot = FakeBot()

        await send_payload_to_chat(
            bot,
            2001,
            {
                "kind": "text",
                "text": "Hello with buttons",
                "buttons": [{"text": "Open", "url": "https://example.com"}],
            },
        )

        keyboard = bot.message_kwargs[0]["reply_markup"]
        self.assertEqual(bot.sent_messages, [(2001, "Hello with buttons")])
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "Open")
        self.assertEqual(keyboard.inline_keyboard[0][0].url, "https://example.com")

    async def test_manage_lists_jobs_with_delete_buttons(self) -> None:
        scheduled_at = datetime(2026, 5, 20, 14, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            job_id = await storage.create_scheduled_job(
                job_type="broadcast",
                text="Manage me",
                payload={"kind": "text", "text": "Manage me"},
                scheduled_at=scheduled_at,
                created_by=1001,
            )
            responder = FakeResponder()

            await send_manage_jobs(responder, storage)

        keyboard = responder.answer_kwargs[-1]["reply_markup"]
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn(f"admin_manage_delete:{job_id}", callbacks)


if __name__ == "__main__":
    unittest.main()
