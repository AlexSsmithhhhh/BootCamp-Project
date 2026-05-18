from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    discord_invite_url: str
    database_path: Path

    @classmethod
    def from_env(cls, env_file: Optional[str | Path] = ".env") -> "Settings":
        if env_file is not None:
            load_dotenv(env_file)

        telegram_bot_token = _required_env("TELEGRAM_BOT_TOKEN")
        discord_invite_url = _required_env("DISCORD_INVITE_URL")
        database_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))

        if not discord_invite_url.startswith(("https://", "http://")):
            raise ConfigurationError("DISCORD_INVITE_URL must be a valid http(s) URL.")

        return cls(
            telegram_bot_token=telegram_bot_token,
            discord_invite_url=discord_invite_url,
            database_path=database_path,
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigurationError(f"{name} is required. Add it to .env or the runtime environment.")
    return value.strip()
