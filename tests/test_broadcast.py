import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import User

from app.admin import send_broadcast
from app.storage import EventStorage


class FakeBot:
    def __init__(self, blocked_ids: set[int] | None = None) -> None:
        self.blocked_ids = blocked_ids or set()
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str):
        if chat_id in self.blocked_ids:
            method = SendMessage(chat_id=chat_id, text=text)
            raise TelegramForbiddenError(method, "bot was blocked by the user")
        self.sent_messages.append((chat_id, text))
        return SimpleNamespace(message_id=len(self.sent_messages))


class BroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_broadcast_sends_to_active_users(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.record_start(User(id=1001, is_bot=False, first_name="Alex"))
            await storage.record_start(User(id=1002, is_bot=False, first_name="Dana"))

            bot = FakeBot()
            result = await send_broadcast(bot, storage, "Hello")

        self.assertEqual(result, {"sent": 2, "failed": 0, "blocked": 0})
        self.assertEqual(bot.sent_messages, [(1001, "Hello"), (1002, "Hello")])

    async def test_send_broadcast_marks_blocked_users(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            storage = EventStorage(Path(tmp_dir) / "bot.sqlite3")
            await storage.init()
            await storage.record_start(User(id=1001, is_bot=False, first_name="Alex"))
            await storage.record_start(User(id=1002, is_bot=False, first_name="Dana"))

            bot = FakeBot(blocked_ids={1002})
            result = await send_broadcast(bot, storage, "Hello")
            overview = await storage.analytics_overview()

        self.assertEqual(result, {"sent": 1, "failed": 1, "blocked": 1})
        self.assertEqual(bot.sent_messages, [(1001, "Hello")])
        self.assertEqual(overview["users_blocked"], 1)


if __name__ == "__main__":
    unittest.main()
