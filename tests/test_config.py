import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_missing_required_env_raises_clear_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "TELEGRAM_BOT_TOKEN is required"):
                Settings.from_env(env_file=None)

    def test_loads_required_env(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "bot.sqlite3"
            env = {
                "TELEGRAM_BOT_TOKEN": "1234567890:test-token",
                "DISCORD_INVITE_URL": "https://discord.gg/test",
                "DATABASE_PATH": str(database_path),
                "TELEGRAM_ADMIN_IDS": "1001, 1002",
                "TELEGRAM_CHANNEL_ID": "-1001234567890",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = Settings.from_env(env_file=None)

        self.assertEqual(settings.telegram_bot_token, env["TELEGRAM_BOT_TOKEN"])
        self.assertEqual(settings.discord_invite_url, env["DISCORD_INVITE_URL"])
        self.assertEqual(settings.database_path, database_path)
        self.assertEqual(settings.telegram_admin_ids, frozenset({1001, 1002}))
        self.assertEqual(settings.telegram_channel_id, "-1001234567890")
        self.assertEqual(settings.scheduler_poll_interval_seconds, 30)


if __name__ == "__main__":
    unittest.main()
