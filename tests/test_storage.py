import unittest
from contextlib import closing
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


if __name__ == "__main__":
    unittest.main()
