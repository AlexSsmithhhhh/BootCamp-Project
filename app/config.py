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
    telegram_admin_ids: frozenset[int]
    telegram_channel_id: Optional[str]
    scheduler_poll_interval_seconds: int

    @classmethod
    def from_env(cls, env_file: Optional[str | Path] = ".env") -> "Settings":
        if env_file is not None:
            load_dotenv(env_file)

        telegram_bot_token = _required_env("TELEGRAM_BOT_TOKEN")
        discord_invite_url = _required_env("DISCORD_INVITE_URL")
        database_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))
        telegram_admin_ids = _optional_int_set("TELEGRAM_ADMIN_IDS")
        telegram_channel_id = _optional_env("TELEGRAM_CHANNEL_ID")
        scheduler_poll_interval_seconds = _optional_positive_int(
            "SCHEDULER_POLL_INTERVAL_SECONDS",
            30,
        )

        if not discord_invite_url.startswith(("https://", "http://")):
            raise ConfigurationError("DISCORD_INVITE_URL must be a valid http(s) URL.")

        return cls(
            telegram_bot_token=telegram_bot_token,
            discord_invite_url=discord_invite_url,
            database_path=database_path,
            telegram_admin_ids=telegram_admin_ids,
            telegram_channel_id=telegram_channel_id,
            scheduler_poll_interval_seconds=scheduler_poll_interval_seconds,
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigurationError(f"{name} is required. Add it to .env or the runtime environment.")
    return value.strip()


def _optional_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _optional_int_set(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "")
    values: set[int] = set()
    for item in raw_value.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        try:
            values.add(int(stripped))
        except ValueError as exc:
            raise ConfigurationError(f"{name} must contain only comma-separated Telegram user IDs.") from exc
    return frozenset(values)


def _optional_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than 0.")
    return value
