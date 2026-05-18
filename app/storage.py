from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from aiogram.types import Contact, User


class EventStorage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone_number TEXT,
                    contact_first_name TEXT,
                    contact_last_name TEXT,
                    contact_received_at TEXT,
                    language_code TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    start_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_telegram_id_created_at
                ON events (telegram_id, created_at)
                """
            )
            await self._ensure_user_contact_columns(db)
            await db.commit()

    async def record_start(self, user: User) -> bool:
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            row = await _fetch_one(
                db,
                "SELECT start_count FROM users WHERE telegram_id = ?",
                (user.id,),
            )
            if row is None:
                await db.execute(
                    """
                    INSERT INTO users (
                        telegram_id, username, first_name, last_name, language_code,
                        first_seen_at, last_seen_at, start_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (*_user_values(user), now, now),
                )
                is_new_user = True
            else:
                await db.execute(
                    """
                    UPDATE users
                    SET username = ?,
                        first_name = ?,
                        last_name = ?,
                        language_code = ?,
                        last_seen_at = ?,
                        start_count = start_count + 1
                    WHERE telegram_id = ?
                    """,
                    (
                        user.username,
                        user.first_name,
                        user.last_name,
                        user.language_code,
                        now,
                        user.id,
                    ),
                )
                is_new_user = False

            await db.commit()

        await self.add_event(user.id, "start" if is_new_user else "start_repeat")
        return is_new_user

    async def ensure_user(self, user: User) -> None:
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            row = await _fetch_one(
                db,
                "SELECT telegram_id FROM users WHERE telegram_id = ?",
                (user.id,),
            )
            if row is None:
                await db.execute(
                    """
                    INSERT INTO users (
                        telegram_id, username, first_name, last_name, language_code,
                        first_seen_at, last_seen_at, start_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (*_user_values(user), now, now),
                )
            else:
                await db.execute(
                    """
                    UPDATE users
                    SET username = ?,
                        first_name = ?,
                        last_name = ?,
                        language_code = ?,
                        last_seen_at = ?
                    WHERE telegram_id = ?
                    """,
                    (
                        user.username,
                        user.first_name,
                        user.last_name,
                        user.language_code,
                        now,
                        user.id,
                    ),
                )
            await db.commit()

    async def add_event(
        self,
        telegram_id: int,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        serialized_payload = None
        if payload is not None:
            serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO events (telegram_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, event_type, serialized_payload, _utc_now()),
            )
            await db.commit()

    async def save_contact(self, user: User, contact: Contact) -> None:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE users
                SET phone_number = ?,
                    contact_first_name = ?,
                    contact_last_name = ?,
                    contact_received_at = ?,
                    last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (
                    contact.phone_number,
                    contact.first_name,
                    contact.last_name,
                    now,
                    now,
                    user.id,
                ),
            )
            await db.commit()

        await self.add_event(
            user.id,
            "contact_shared",
            {
                "has_phone_number": bool(contact.phone_number),
                "contact_user_id": contact.user_id,
            },
        )

    async def _ensure_user_contact_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(users)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        required_columns = {
            "phone_number": "TEXT",
            "contact_first_name": "TEXT",
            "contact_last_name": "TEXT",
            "contact_received_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")


async def _fetch_one(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[Any, ...],
) -> Optional[aiosqlite.Row]:
    async with db.execute(query, parameters) as cursor:
        return await cursor.fetchone()


def _user_values(user: User) -> tuple[int, Optional[str], str, Optional[str], Optional[str]]:
    return (
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        user.language_code,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
