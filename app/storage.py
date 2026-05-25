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
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    current_question_index INTEGER NOT NULL DEFAULT 0,
                    answers TEXT NOT NULL DEFAULT '[]',
                    scores TEXT NOT NULL DEFAULT '{}',
                    result_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metadata TEXT,
                    assigned_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id),
                    UNIQUE (telegram_id, source)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    invite_code TEXT NOT NULL UNIQUE,
                    invite_url TEXT NOT NULL,
                    channel_id TEXT,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    max_age_seconds INTEGER,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_error TEXT,
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
            await self._ensure_user_analytics_columns(db)
            await self._ensure_user_quiz_columns(db)
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
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_status_updated
                ON quiz_attempts (telegram_id, status, updated_at)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_tags_tag_source
                ON user_tags (tag, source)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_quiz_result_tag
                ON users (quiz_result_tag)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_discord_invites_user_status_expires
                ON discord_invites (telegram_id, status, expires_at, created_at)
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

    async def mark_discord_open_clicked(self, user: User) -> None:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE users
                SET discord_open_clicked_at = COALESCE(discord_open_clicked_at, ?),
                    last_interaction_at = ?
                WHERE telegram_id = ?
                """,
                (now, now, user.id),
            )
            await db.commit()

        await self.add_event(user.id, "discord_open_clicked")

    async def latest_active_discord_invite(self, telegram_id: int) -> Optional[dict[str, Any]]:
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await _fetch_one(
                db,
                """
                SELECT *
                FROM discord_invites
                WHERE telegram_id = ?
                  AND status = 'active'
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (telegram_id, now),
            )
        if row is None:
            return None
        return _discord_invite_from_row(row)

    async def save_discord_invite(
        self,
        user: User,
        *,
        invite_code: str,
        invite_url: str,
        channel_id: Optional[str],
        max_uses: int,
        max_age_seconds: Optional[int],
        expires_at: Optional[str],
    ) -> dict[str, Any]:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                UPDATE discord_invites
                SET status = 'replaced'
                WHERE telegram_id = ?
                  AND status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (user.id, now),
            )
            cursor = await db.execute(
                """
                INSERT INTO discord_invites (
                    telegram_id, invite_code, invite_url, channel_id, max_uses,
                    max_age_seconds, status, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    user.id,
                    invite_code,
                    invite_url,
                    channel_id,
                    max_uses,
                    max_age_seconds,
                    now,
                    expires_at,
                ),
            )
            row = await _fetch_one(
                db,
                "SELECT * FROM discord_invites WHERE id = ?",
                (cursor.lastrowid,),
            )
            await db.commit()

        await self.add_event(
            user.id,
            "discord_invite_generated",
            {
                "invite_code": invite_code,
                "channel_id": channel_id,
                "max_uses": max_uses,
                "max_age_seconds": max_age_seconds,
                "expires_at": expires_at,
            },
        )
        if row is None:
            raise RuntimeError("Discord invite disappeared after saving")
        return _discord_invite_from_row(row)

    async def mark_discord_invite_generation_failed(self, user: User, error: str) -> None:
        await self.ensure_user(user)
        await self.add_event(
            user.id,
            "discord_invite_generation_failed",
            {
                "error": error[:500],
            },
        )

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

    async def start_quiz_attempt(self, user: User) -> dict[str, Any]:
        await self.ensure_user(user)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE quiz_attempts
                SET status = 'abandoned',
                    updated_at = ?
                WHERE telegram_id = ?
                  AND status = 'in_progress'
                """,
                (now, user.id),
            )
            cursor = await db.execute(
                """
                INSERT INTO quiz_attempts (
                    telegram_id, status, current_question_index, answers, scores,
                    created_at, updated_at
                )
                VALUES (?, 'in_progress', 0, '[]', '{}', ?, ?)
                """,
                (user.id, now, now),
            )
            await db.commit()
            attempt_id = int(cursor.lastrowid)

        await self.add_event(user.id, "quiz_started", {"attempt_id": attempt_id})
        attempt = await self.quiz_attempt(attempt_id)
        if attempt is None:
            raise RuntimeError("Quiz attempt was not created")
        return attempt

    async def quiz_attempt(self, attempt_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await _fetch_one(
                db,
                """
                SELECT *
                FROM quiz_attempts
                WHERE id = ?
                """,
                (attempt_id,),
            )
        if row is None:
            return None
        return _quiz_attempt_from_row(row)

    async def active_quiz_attempt(self, telegram_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await _fetch_one(
                db,
                """
                SELECT *
                FROM quiz_attempts
                WHERE telegram_id = ?
                  AND status = 'in_progress'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (telegram_id,),
            )
        if row is None:
            return None
        return _quiz_attempt_from_row(row)

    async def latest_completed_quiz_attempt(
        self,
        telegram_id: int,
    ) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await _fetch_one(
                db,
                """
                SELECT *
                FROM quiz_attempts
                WHERE telegram_id = ?
                  AND status = 'completed'
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """,
                (telegram_id,),
            )
        if row is None:
            return None
        return _quiz_attempt_from_row(row)

    async def record_quiz_answer(
        self,
        *,
        user: User,
        attempt_id: int,
        question_index: int,
        answer_key: str,
        category: str,
        category_label: str,
    ) -> dict[str, Any]:
        attempt = await self.quiz_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"Quiz attempt {attempt_id} does not exist")
        if attempt["telegram_id"] != user.id:
            raise ValueError("Quiz attempt belongs to another user")
        if attempt["status"] != "in_progress":
            raise ValueError("Quiz attempt is not in progress")
        if attempt["current_question_index"] != question_index:
            raise ValueError("Quiz question index is stale")

        answers = list(attempt["answers"])
        scores = dict(attempt["scores"])
        answers.append(
            {
                "question_index": question_index,
                "answer_key": answer_key,
                "category": category,
            }
        )
        scores[category] = int(scores.get(category, 0)) + 1
        now = _utc_now()
        next_question_index = question_index + 1
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE quiz_attempts
                SET current_question_index = ?,
                    answers = ?,
                    scores = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_question_index,
                    json.dumps(answers, ensure_ascii=False, sort_keys=True),
                    json.dumps(scores, ensure_ascii=False, sort_keys=True),
                    now,
                    attempt_id,
                ),
            )
            await db.commit()

        await self.add_event(
            user.id,
            "quiz_answered",
            {
                "attempt_id": attempt_id,
                "question_index": question_index,
                "answer_key": answer_key,
                "category": category,
                "category_label": category_label,
            },
        )
        updated_attempt = await self.quiz_attempt(attempt_id)
        if updated_attempt is None:
            raise RuntimeError("Quiz attempt disappeared after answer")
        return updated_attempt

    async def rewind_quiz_attempt(
        self,
        *,
        user: User,
        attempt_id: int,
        current_question_index: int,
    ) -> dict[str, Any]:
        attempt = await self.quiz_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"Quiz attempt {attempt_id} does not exist")
        if attempt["telegram_id"] != user.id:
            raise ValueError("Quiz attempt belongs to another user")
        if attempt["status"] != "in_progress":
            raise ValueError("Quiz attempt is not in progress")
        if attempt["current_question_index"] != current_question_index:
            raise ValueError("Quiz question index is stale")
        if current_question_index <= 0:
            raise ValueError("Quiz attempt is already at the first question")

        answers = list(attempt["answers"])
        if not answers:
            raise ValueError("Quiz attempt has no answers to rewind")
        removed_answer = answers.pop()
        previous_question_index = current_question_index - 1
        if int(removed_answer["question_index"]) != previous_question_index:
            raise ValueError("Quiz answer history is inconsistent")

        scores = dict(attempt["scores"])
        removed_category = str(removed_answer["category"])
        scores[removed_category] = max(0, int(scores.get(removed_category, 0)) - 1)
        now = _utc_now()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE quiz_attempts
                SET current_question_index = ?,
                    answers = ?,
                    scores = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    previous_question_index,
                    json.dumps(answers, ensure_ascii=False, sort_keys=True),
                    json.dumps(scores, ensure_ascii=False, sort_keys=True),
                    now,
                    attempt_id,
                ),
            )
            await db.commit()

        await self.add_event(
            user.id,
            "quiz_answer_rewound",
            {
                "attempt_id": attempt_id,
                "question_index": previous_question_index,
                "answer_key": removed_answer["answer_key"],
                "category": removed_category,
            },
        )
        updated_attempt = await self.quiz_attempt(attempt_id)
        if updated_attempt is None:
            raise RuntimeError("Quiz attempt disappeared after rewind")
        return updated_attempt

    async def complete_quiz_attempt(
        self,
        *,
        user: User,
        attempt_id: int,
        result_key: str,
        result_tag: Optional[str] = None,
        scores: dict[str, int],
    ) -> dict[str, Any]:
        now = _utc_now()
        serialized_scores = json.dumps(scores, ensure_ascii=False, sort_keys=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE quiz_attempts
                SET status = 'completed',
                    result_key = ?,
                    scores = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND telegram_id = ?
                """,
                (
                    result_key,
                    serialized_scores,
                    now,
                    now,
                    attempt_id,
                    user.id,
                ),
            )
            await db.execute(
                """
                UPDATE users
                SET quiz_result_key = ?,
                    quiz_result_tag = ?,
                    quiz_scores = ?,
                    quiz_completed_at = ?,
                    last_interaction_at = ?
                WHERE telegram_id = ?
                """,
                (
                    result_key,
                    result_tag,
                    serialized_scores,
                    now,
                    now,
                    user.id,
                ),
            )
            if result_tag is not None:
                await db.execute(
                    """
                    INSERT INTO user_tags (
                        telegram_id, tag, source, metadata, assigned_at, updated_at
                    )
                    VALUES (?, ?, 'quiz_result', ?, ?, ?)
                    ON CONFLICT(telegram_id, source) DO UPDATE SET
                        tag = excluded.tag,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user.id,
                        result_tag,
                        json.dumps(
                            {
                                "attempt_id": attempt_id,
                                "result_key": result_key,
                                "scores": scores,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        now,
                        now,
                    ),
                )
            await db.commit()

        await self.add_event(
            user.id,
            "quiz_completed",
            {
                "attempt_id": attempt_id,
                "result_key": result_key,
                "result_tag": result_tag,
                "scores": scores,
            },
        )
        if result_tag is not None:
            await self.add_event(
                user.id,
                "user_tag_assigned",
                {
                    "tag": result_tag,
                    "source": "quiz_result",
                    "attempt_id": attempt_id,
                },
            )
        attempt = await self.quiz_attempt(attempt_id)
        if attempt is None:
            raise RuntimeError("Quiz attempt disappeared after completion")
        return attempt

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
            "discord_open_clicked_at": "TEXT",
            "last_delivery_error": "TEXT",
            "last_delivery_error_at": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

    async def _ensure_user_quiz_columns(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(users)") as cursor:
            existing_columns = {row[1] for row in await cursor.fetchall()}

        required_columns = {
            "quiz_result_key": "TEXT",
            "quiz_result_tag": "TEXT",
            "quiz_scores": "TEXT",
            "quiz_completed_at": "TEXT",
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


def _quiz_attempt_from_row(row: aiosqlite.Row) -> dict[str, Any]:
    attempt = dict(row)
    attempt["answers"] = _json_object(attempt.get("answers"), default=[])
    attempt["scores"] = _json_object(attempt.get("scores"), default={})
    return attempt


def _discord_invite_from_row(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


def _json_object(value: Optional[str], *, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


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
