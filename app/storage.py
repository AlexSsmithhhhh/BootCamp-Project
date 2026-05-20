from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs

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
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    text TEXT NOT NULL,
                    payload TEXT,
                    target_chat_id TEXT,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    sent_at TEXT,
                    telegram_message_id INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_media_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    media_group_id TEXT,
                    message_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    caption TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(admin_id, message_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_post_drafts (
                    admin_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scheduled_at TEXT,
                    media_group_id TEXT,
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
            await self._ensure_user_analytics_columns(db)
            await self._ensure_scheduled_job_columns(db)
            await self._ensure_admin_post_draft_columns(db)
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_event_type_created_at
                ON events (event_type, created_at)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_created_at
                ON events (created_at)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_subscription_status
                ON users (subscription_status)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_source
                ON users (source)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_status_scheduled_at
                ON scheduled_jobs (status, scheduled_at)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_admin_media_cache_admin_group
                ON admin_media_cache (admin_id, media_group_id, message_id)
                """
            )
            await db.commit()

    async def record_start(self, user: User, start_payload: Optional[str] = None) -> bool:
        now = _utc_now()
        source = _source_from_payload(start_payload)
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
                        first_seen_at, last_seen_at, start_count, subscription_status,
                        subscribed_at, last_interaction_at, start_payload, source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, ?, ?)
                    """,
                    (*_user_values(user), now, now, now, now, start_payload, source),
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
                        last_interaction_at = ?,
                        subscription_status = 'active',
                        unsubscribed_at = NULL,
                        subscribed_at = COALESCE(subscribed_at, ?),
                        start_payload = COALESCE(start_payload, ?),
                        source = COALESCE(source, ?),
                        start_count = start_count + 1
                    WHERE telegram_id = ?
                    """,
                    (
                        user.username,
                        user.first_name,
                        user.last_name,
                        user.language_code,
                        now,
                        now,
                        now,
                        start_payload,
                        source,
                        user.id,
                    ),
                )
                is_new_user = False

            await db.commit()

        await self.add_event(
            user.id,
            "start" if is_new_user else "start_repeat",
            {
                "start_payload": start_payload,
                "source": source,
            },
        )
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
                        last_seen_at = ?,
                        last_interaction_at = ?
                    WHERE telegram_id = ?
                    """,
                    (
                        user.username,
                        user.first_name,
                        user.last_name,
                        user.language_code,
                        now,
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
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO users (
                    telegram_id, username, first_name, last_name, language_code,
                    phone_number, contact_first_name, contact_last_name,
                    contact_received_at, first_seen_at, last_seen_at, start_count,
                    subscription_status, subscribed_at, last_interaction_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    language_code = excluded.language_code,
                    phone_number = excluded.phone_number,
                    contact_first_name = excluded.contact_first_name,
                    contact_last_name = excluded.contact_last_name,
                    contact_received_at = excluded.contact_received_at,
                    last_seen_at = excluded.last_seen_at,
                    last_interaction_at = excluded.last_interaction_at,
                    subscription_status = 'active',
                    unsubscribed_at = NULL,
                    subscribed_at = COALESCE(users.subscribed_at, excluded.subscribed_at)
                """,
                (
                    *_user_values(user),
                    contact.phone_number,
                    contact.first_name,
                    contact.last_name,
                    now,
                    now,
                    now,
                    now,
                    now,
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

    async def record_message_interaction(
        self,
        user: User,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        await self.ensure_user(user)
        await self.add_event(user.id, event_type, payload)

    async def mark_discord_access_sent(self, user: User) -> None:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE users
                SET discord_invite_sent_at = COALESCE(discord_invite_sent_at, ?),
                    last_interaction_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, user.id),
            )
            await db.commit()

        await self.add_event(user.id, "discord_access_sent")

    async def mark_delivery_failed(self, telegram_id: int, error: str) -> None:
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE users
                SET subscription_status = 'blocked',
                    unsubscribed_at = COALESCE(unsubscribed_at, ?),
                    last_delivery_error = ?,
                    last_delivery_error_at = ?
                WHERE telegram_id = ?
                """,
                (now, error[:500], now, telegram_id),
            )
            await db.commit()

        await self.add_event(
            telegram_id,
            "delivery_failed",
            {
                "error": error[:500],
            },
        )

    async def active_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.database_path) as db:
            async with db.execute(
                """
                SELECT telegram_id
                FROM users
                WHERE subscription_status = 'active'
                ORDER BY first_seen_at
                """
            ) as cursor:
                rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def user_has_contact(self, telegram_id: int) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            row = await _fetch_one(
                db,
                """
                SELECT 1
                WHERE EXISTS (
                    SELECT 1
                    FROM users
                    WHERE telegram_id = ?
                      AND (
                        contact_received_at IS NOT NULL
                        OR phone_number IS NOT NULL
                        OR discord_invite_sent_at IS NOT NULL
                      )
                )
                OR EXISTS (
                    SELECT 1
                    FROM events
                    WHERE telegram_id = ?
                      AND event_type IN ('contact_shared', 'discord_access_sent')
                )
                """,
                (telegram_id, telegram_id),
            )
        return row is not None

    async def should_prompt_contact(
        self,
        telegram_id: int,
        cooldown_seconds: int = 600,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            row = await _fetch_one(
                db,
                """
                SELECT
                    phone_number,
                    contact_received_at,
                    discord_invite_sent_at,
                    last_contact_prompt_at
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )

        if row is None:
            return True

        phone_number, contact_received_at, discord_invite_sent_at, last_contact_prompt_at = row
        if phone_number or contact_received_at or discord_invite_sent_at:
            return False
        if not last_contact_prompt_at:
            return True

        try:
            last_prompt_dt = datetime.fromisoformat(last_contact_prompt_at)
        except ValueError:
            return True
        if last_prompt_dt.tzinfo is None:
            last_prompt_dt = last_prompt_dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return now - last_prompt_dt >= timedelta(seconds=cooldown_seconds)

    async def mark_contact_prompted(self, user: User) -> None:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE users
                SET last_contact_prompt_at = ?,
                    last_seen_at = ?,
                    last_interaction_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, now, user.id),
            )
            await db.commit()

        await self.add_event(user.id, "contact_prompt_sent")

    async def create_scheduled_job(
        self,
        *,
        job_type: str,
        text: str,
        scheduled_at: datetime,
        created_by: int,
        target_chat_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        now = _utc_now()
        serialized_payload = None
        if payload is not None:
            serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO scheduled_jobs (
                    job_type, status, text, payload, target_chat_id, created_by,
                    created_at, scheduled_at
                )
                VALUES (?, 'scheduled', ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_type,
                    text,
                    serialized_payload,
                    target_chat_id,
                    created_by,
                    now,
                    _datetime_to_utc_iso(scheduled_at),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def due_scheduled_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM scheduled_jobs
                WHERE status = 'scheduled'
                  AND scheduled_at <= ?
                ORDER BY scheduled_at, id
                LIMIT ?
                """,
                (now, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_job_processing(self, job_id: int) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'processing',
                    attempts = attempts + 1,
                    last_error = NULL
                WHERE id = ?
                  AND status = 'scheduled'
                """,
                (job_id,),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def mark_job_sent(
        self,
        job_id: int,
        *,
        telegram_message_id: Optional[int] = None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'sent',
                    sent_at = ?,
                    telegram_message_id = ?
                WHERE id = ?
                """,
                (_utc_now(), telegram_message_id, job_id),
            )
            await db.commit()

    async def mark_job_failed(self, job_id: int, error: str) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'failed',
                    last_error = ?
                WHERE id = ?
                """,
                (error[:500], job_id),
            )
            await db.commit()

    async def cancel_scheduled_job(self, job_id: int) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'cancelled'
                WHERE id = ?
                  AND status = 'scheduled'
                """,
                (job_id,),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def list_scheduled_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, job_type, status, scheduled_at, target_chat_id, text, payload
                FROM scheduled_jobs
                WHERE status = 'scheduled'
                ORDER BY scheduled_at, id
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_admin_post_draft(
        self,
        *,
        admin_id: int,
        mode: str,
        status: str,
        scheduled_at: Optional[datetime] = None,
        media_group_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        now = _utc_now()
        scheduled_at_value = None
        if scheduled_at is not None:
            scheduled_at_value = _datetime_to_utc_iso(scheduled_at)
        serialized_payload = None
        if payload is not None:
            serialized_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO admin_post_drafts (
                    admin_id, mode, status, scheduled_at, media_group_id, payload,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(admin_id) DO UPDATE SET
                    mode = excluded.mode,
                    status = excluded.status,
                    scheduled_at = excluded.scheduled_at,
                    media_group_id = excluded.media_group_id,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    admin_id,
                    mode,
                    status,
                    scheduled_at_value,
                    media_group_id,
                    serialized_payload,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def admin_post_draft(self, admin_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await _fetch_one(
                db,
                """
                SELECT admin_id, mode, status, scheduled_at, media_group_id,
                       payload, created_at, updated_at
                FROM admin_post_drafts
                WHERE admin_id = ?
                """,
                (admin_id,),
            )
        if row is None:
            return None
        return dict(row)

    async def clear_admin_post_draft(self, admin_id: int) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "DELETE FROM admin_post_drafts WHERE admin_id = ?",
                (admin_id,),
            )
            await db.commit()

    async def save_admin_media(
        self,
        *,
        admin_id: int,
        message_id: int,
        media_type: str,
        file_id: str,
        media_group_id: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO admin_media_cache (
                    admin_id, media_group_id, message_id, media_type,
                    file_id, caption, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(admin_id, message_id) DO UPDATE SET
                    media_group_id = excluded.media_group_id,
                    media_type = excluded.media_type,
                    file_id = excluded.file_id,
                    caption = excluded.caption,
                    created_at = excluded.created_at
                """,
                (
                    admin_id,
                    media_group_id,
                    message_id,
                    media_type,
                    file_id,
                    caption,
                    _utc_now(),
                ),
            )
            await db.commit()

    async def admin_media_group(
        self,
        *,
        admin_id: int,
        media_group_id: str,
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT media_type, file_id, caption, message_id
                FROM admin_media_cache
                WHERE admin_id = ?
                  AND media_group_id = ?
                ORDER BY message_id
                """,
                (admin_id, media_group_id),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def prune_admin_media_cache(self, keep_latest: int = 200) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                DELETE FROM admin_media_cache
                WHERE id NOT IN (
                    SELECT id
                    FROM admin_media_cache
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (keep_latest,),
            )
            await db.commit()

    async def analytics_overview(self) -> dict[str, int]:
        last_24h = _datetime_to_utc_iso(datetime.now(timezone.utc) - timedelta(days=1))
        last_7d = _datetime_to_utc_iso(datetime.now(timezone.utc) - timedelta(days=7))
        async with aiosqlite.connect(self.database_path) as db:
            totals = {
                "users_total": await _fetch_count(db, "SELECT COUNT(*) FROM users"),
                "users_active": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE subscription_status = 'active'",
                ),
                "users_blocked": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE subscription_status = 'blocked'",
                ),
                "contacts_shared": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE contact_received_at IS NOT NULL",
                ),
                "discord_invites_sent": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE discord_invite_sent_at IS NOT NULL",
                ),
                "users_last_24h": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE first_seen_at >= ?",
                    (last_24h,),
                ),
                "users_last_7d": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE first_seen_at >= ?",
                    (last_7d,),
                ),
                "contacts_last_7d": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM users WHERE contact_received_at >= ?",
                    (last_7d,),
                ),
                "starts_total": await _fetch_count(
                    db,
                    "SELECT COUNT(*) FROM events WHERE event_type IN ('start', 'start_repeat')",
                ),
                "events_total": await _fetch_count(db, "SELECT COUNT(*) FROM events"),
            }
        return totals

    async def analytics_sources(self, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    CASE
                        WHEN source IS NULL OR TRIM(source) = '' THEN 'direct'
                        ELSE source
                    END AS source,
                    COUNT(*) AS users_total,
                    SUM(CASE WHEN subscription_status = 'active' THEN 1 ELSE 0 END) AS users_active,
                    SUM(CASE WHEN contact_received_at IS NOT NULL THEN 1 ELSE 0 END) AS contacts_shared,
                    SUM(CASE WHEN discord_invite_sent_at IS NOT NULL THEN 1 ELSE 0 END) AS discord_invites_sent
                FROM users
                GROUP BY
                    CASE
                        WHEN source IS NULL OR TRIM(source) = '' THEN 'direct'
                        ELSE source
                    END
                ORDER BY users_total DESC, source
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _ensure_user_contact_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(users)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        required_columns = {
            "phone_number": "TEXT",
            "contact_first_name": "TEXT",
            "contact_last_name": "TEXT",
            "contact_received_at": "TEXT",
            "last_contact_prompt_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

    async def _ensure_user_analytics_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(users)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        required_columns = {
            "subscription_status": "TEXT NOT NULL DEFAULT 'active'",
            "subscribed_at": "TEXT",
            "unsubscribed_at": "TEXT",
            "last_interaction_at": "TEXT",
            "start_payload": "TEXT",
            "source": "TEXT",
            "discord_invite_sent_at": "TEXT",
            "last_delivery_error": "TEXT",
            "last_delivery_error_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

    async def _ensure_scheduled_job_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(scheduled_jobs)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        if "payload" not in existing_columns:
            await db.execute("ALTER TABLE scheduled_jobs ADD COLUMN payload TEXT")

    async def _ensure_admin_post_draft_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(admin_post_drafts)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        if "payload" not in existing_columns:
            await db.execute("ALTER TABLE admin_post_drafts ADD COLUMN payload TEXT")


async def _fetch_one(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[Any, ...],
) -> Optional[aiosqlite.Row]:
    async with db.execute(query, parameters) as cursor:
        return await cursor.fetchone()


async def _fetch_count(
    db: aiosqlite.Connection,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> int:
    async with db.execute(query, parameters) as cursor:
        row = await cursor.fetchone()
    return int(row[0])


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


def _datetime_to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _source_from_payload(start_payload: Optional[str]) -> Optional[str]:
    if not start_payload:
        return None
    normalized_payload = start_payload.strip()
    if "=" not in normalized_payload:
        lowered_payload = normalized_payload.lower()
        for prefix in ("utm_source_", "source_", "src_", "campaign_", "segment_"):
            if lowered_payload.startswith(prefix):
                extracted = normalized_payload[len(prefix) :].strip("_-")
                return (extracted or normalized_payload)[:100]
        return normalized_payload[:100]
    parsed = parse_qs(normalized_payload, keep_blank_values=False)
    for key in ("utm_source", "source", "src", "campaign", "segment"):
        values = parsed.get(key)
        if values:
            return values[0][:100]
    return normalized_payload[:100]
