import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from app.admin import (
    is_admin_identity,
    normalize_plain_command,
    parse_media_caption_command,
    parse_post_schedule_input,
)
from app.config import Settings


class AdminCommandTests(unittest.TestCase):
    def test_parses_direct_media_post_caption(self) -> None:
        self.assertEqual(
            parse_media_caption_command("/post Photo caption"),
            ("post", "Photo caption"),
        )

    def test_parses_direct_media_broadcast_caption_with_bot_name(self) -> None:
        self.assertEqual(
            parse_media_caption_command("/broadcast@BootcampBot Broadcast caption"),
            ("broadcast", "Broadcast caption"),
        )

    def test_ignores_regular_caption(self) -> None:
        self.assertIsNone(parse_media_caption_command("Regular photo caption"))

    def test_normalizes_plain_commands(self) -> None:
        self.assertEqual(normalize_plain_command("/new_post"), "new post")
        self.assertEqual(normalize_plain_command("/newpost"), "new post")
        self.assertEqual(normalize_plain_command("all post"), "all post")
        self.assertEqual(normalize_plain_command("allpost"), "all post")
        self.assertEqual(normalize_plain_command("/delete 7"), "delete 7")

    def test_parses_post_schedule_input_as_utc(self) -> None:
        parsed = parse_post_schedule_input("2026-05-20 14:00")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_admin_identity_supports_ids_and_usernames(self) -> None:
        settings = Settings(
            telegram_bot_token="token",
            discord_invite_url="https://discord.gg/test",
            database_path=Path("data/bot.sqlite3"),
            telegram_admin_ids=frozenset({1001}),
            telegram_admin_usernames=frozenset({"qweertyck"}),
            telegram_channel_id="@channel",
            scheduler_poll_interval_seconds=30,
        )

        self.assertTrue(is_admin_identity(1001, None, settings))
        self.assertTrue(is_admin_identity(2002, "qweertyck", settings))
        self.assertTrue(is_admin_identity(2002, "QWEERTYCK", settings))
        self.assertFalse(is_admin_identity(2002, "someoneelse", settings))

    def test_settings_reads_admin_usernames(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "token",
            "DISCORD_INVITE_URL": "https://discord.gg/test",
            "TELEGRAM_ADMIN_USERNAMES": "@qweertyck, smthhhhhh",
        }

        with patch.dict("os.environ", env, clear=True):
            settings = Settings.from_env(env_file=None)

        self.assertEqual(
            settings.telegram_admin_usernames,
            frozenset({"qweertyck", "smthhhhhh"}),
        )


if __name__ == "__main__":
    unittest.main()
