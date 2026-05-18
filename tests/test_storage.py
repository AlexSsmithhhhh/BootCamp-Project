import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram.types import User

from app.storage import EventStorage


class EventStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_starts_and_discord_click(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            storage = EventStorage(database_path)
            await storage.init()

            user = User(id=1001, is_bot=False, first_name="Alex", username="alex")

            self.assertTrue(await storage.record_start(user))
            self.assertFalse(await storage.record_start(user))
            await storage.add_event(user.id, "discord_cta_click")

            with sqlite3.connect(database_path) as db:
                start_count = db.execute(
                    "SELECT start_count FROM users WHERE telegram_id = ?",
                    (user.id,),
                ).fetchone()[0]
                event_types = [
                    row[0]
                    for row in db.execute(
                        "SELECT event_type FROM events ORDER BY id"
                    ).fetchall()
                ]

        self.assertEqual(start_count, 2)
        self.assertEqual(event_types, ["start", "start_repeat", "discord_cta_click"])


if __name__ == "__main__":
    unittest.main()
