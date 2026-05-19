from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone, tzinfo
from html import escape
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import InputMediaPhoto, Message

from app.config import Settings
from app.storage import EventStorage


Payload = dict[str, Any]


class AdminOnly(BaseFilter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return is_admin(message, settings)


def is_admin(message: Message, settings: Settings) -> bool:
    return bool(message.from_user and message.from_user.id in settings.telegram_admin_ids)


async def deny_non_admin(message: Message) -> None:
    await message.answer("Команда доступна только администратору.")


def admin_commands(router) -> None:
    @router.message(AdminOnly(), F.photo | F.video | F.document)
    async def handle_admin_media_upload(
        message: Message,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if message.from_user is None:
            return
        media = media_from_message(message)
        if media is None:
            return
        await storage.ensure_user(message.from_user)
        await storage.save_admin_media(
            admin_id=message.from_user.id,
            message_id=message.message_id,
            media_group_id=message.media_group_id,
            media_type=media["kind"],
            file_id=media["file_id"],
            caption=message.caption,
        )
        await storage.prune_admin_media_cache()

        caption_command = parse_media_caption_command(message.caption)
        if caption_command is not None:
            action, caption = caption_command
            if message.media_group_id and media["kind"] == "photo":
                asyncio.create_task(
                    execute_media_group_caption_action(
                        message=message,
                        bot=bot,
                        storage=storage,
                        settings=settings,
                        action=action,
                        caption=caption,
                        admin_id=message.from_user.id,
                        media_group_id=message.media_group_id,
                    )
                )
                return

            await execute_direct_media_action(
                message=message,
                bot=bot,
                storage=storage,
                settings=settings,
                action=action,
                payload={
                    "kind": media["kind"],
                    "file_id": media["file_id"],
                    "caption": caption,
                },
            )
            return

        if message.media_group_id is None:
            await message.answer(
                "Медиа сохранено. Ответь на это сообщение командой /post, "
                "/broadcast, /schedule_post YYYY-MM-DD HH:MM или "
                "/schedule_broadcast YYYY-MM-DD HH:MM."
            )

    @router.message(Command("admin_help"))
    async def handle_admin_help(message: Message, settings: Settings) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await message.answer(
            "\n".join(
                [
                    "<b>Admin-команды</b>",
                    "/post текст - сразу опубликовать текст в канал",
                    "/post - ответом на фото/альбом/видео/PDF публикует это медиа",
                    "Фото/видео/PDF с caption `/post текст` публикуется сразу",
                    "/delete_post message_id - удалить пост из канала",
                    "/broadcast текст - отправить рассылку всем активным пользователям",
                    "/broadcast - ответом на медиа отправляет медиа-рассылку",
                    "Фото/видео/PDF с caption `/broadcast текст` сразу запускает рассылку",
                    "/schedule_post YYYY-MM-DD HH:MM | текст - запланировать пост",
                    "/schedule_post YYYY-MM-DD HH:MM - ответом на медиа планирует медиа-пост",
                    "/schedule_broadcast YYYY-MM-DD HH:MM | текст - запланировать рассылку",
                    "/schedule_broadcast YYYY-MM-DD HH:MM - ответом на медиа планирует медиа-рассылку",
                    "/scheduled - показать ближайшие задания",
                    "/cancel_scheduled id - отменить задание",
                ]
            )
        )

    @router.message(Command("post"))
    async def handle_post(
        message: Message,
        command: CommandObject,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        channel_id = require_channel_id(settings)
        if channel_id is None:
            await message.answer("Не задан TELEGRAM_CHANNEL_ID.")
            return
        await storage.ensure_user(message.from_user)
        payload = await build_message_payload(message, storage, command.args)
        if payload is None:
            await message.answer(
                "Формат: /post текст. Для медиа отправь фото/альбом/видео/PDF "
                "боту и ответь на него командой /post."
            )
            return
        sent_messages = await send_payload_to_chat(bot, channel_id, payload)
        first_message_id = sent_messages[0].message_id if sent_messages else None
        await storage.add_event(
            message.from_user.id,
            "admin_channel_post_sent",
            {
                "message_id": first_message_id,
                "payload_kind": payload["kind"],
            },
        )
        await message.answer(
            "Пост опубликован. "
            f"Message ID: <code>{first_message_id}</code>"
        )

    @router.message(Command("delete_post"))
    async def handle_delete_post(
        message: Message,
        command: CommandObject,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        channel_id = require_channel_id(settings)
        if channel_id is None:
            await message.answer("Не задан TELEGRAM_CHANNEL_ID.")
            return
        await storage.ensure_user(message.from_user)
        message_id = parse_int(command.args)
        if message_id is None:
            await message.answer("Формат: /delete_post message_id")
            return
        try:
            await bot.delete_message(channel_id, message_id)
        except TelegramBadRequest as exc:
            await message.answer(f"Не удалось удалить пост: {escape(str(exc))}")
            return
        await storage.add_event(
            message.from_user.id,
            "admin_channel_post_deleted",
            {"message_id": message_id},
        )
        await message.answer(f"Пост <code>{message_id}</code> удален.")

    @router.message(Command("broadcast"))
    async def handle_broadcast(
        message: Message,
        command: CommandObject,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        payload = await build_message_payload(message, storage, command.args)
        if payload is None:
            await message.answer(
                "Формат: /broadcast текст. Для медиа отправь фото/альбом/видео/PDF "
                "боту и ответь на него командой /broadcast."
            )
            return
        await storage.ensure_user(message.from_user)
        result = await send_broadcast(bot, storage, payload)
        await storage.add_event(
            message.from_user.id,
            "admin_broadcast_sent",
            {"payload_kind": payload["kind"], **result},
        )
        await message.answer(format_broadcast_result(result))

    @router.message(Command("schedule_post"))
    async def handle_schedule_post(
        message: Message,
        command: CommandObject,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        channel_id = require_channel_id(settings)
        if channel_id is None:
            await message.answer("Не задан TELEGRAM_CHANNEL_ID.")
            return
        await storage.ensure_user(message.from_user)
        parsed = parse_scheduled_command(command.args)
        if parsed is None:
            await message.answer("Формат: /schedule_post YYYY-MM-DD HH:MM | текст поста")
            return
        scheduled_at, text = parsed
        payload = await build_message_payload(message, storage, text)
        if payload is None:
            await message.answer(
                "Формат: /schedule_post YYYY-MM-DD HH:MM | текст. "
                "Для медиа ответь командой на фото/альбом/видео/PDF."
            )
            return
        job_id = await storage.create_scheduled_job(
            job_type="channel_post",
            text=payload_preview(payload),
            payload=payload,
            target_chat_id=str(channel_id),
            scheduled_at=scheduled_at,
            created_by=message.from_user.id,
        )
        await message.answer(f"Пост запланирован. ID: <code>{job_id}</code>")

    @router.message(Command("schedule_broadcast"))
    async def handle_schedule_broadcast(
        message: Message,
        command: CommandObject,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        parsed = parse_scheduled_command(command.args)
        if parsed is None:
            await message.answer("Формат: /schedule_broadcast YYYY-MM-DD HH:MM | текст рассылки")
            return
        await storage.ensure_user(message.from_user)
        scheduled_at, text = parsed
        payload = await build_message_payload(message, storage, text)
        if payload is None:
            await message.answer(
                "Формат: /schedule_broadcast YYYY-MM-DD HH:MM | текст. "
                "Для медиа ответь командой на фото/альбом/видео/PDF."
            )
            return
        job_id = await storage.create_scheduled_job(
            job_type="broadcast",
            text=payload_preview(payload),
            payload=payload,
            scheduled_at=scheduled_at,
            created_by=message.from_user.id,
        )
        await message.answer(f"Рассылка запланирована. ID: <code>{job_id}</code>")

    @router.message(Command("scheduled"))
    async def handle_scheduled(
        message: Message,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        jobs = await storage.list_scheduled_jobs()
        if not jobs:
            await message.answer("Запланированных заданий нет.")
            return
        lines = ["<b>Запланировано</b>"]
        for job in jobs:
            preview = escape(payload_preview(payload_from_job(job))[:120])
            lines.append(
                f"#{job['id']} · {job['job_type']} · {job['scheduled_at']}\n{preview}"
            )
        await message.answer("\n\n".join(lines))

    @router.message(Command("cancel_scheduled"))
    async def handle_cancel_scheduled(
        message: Message,
        command: CommandObject,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        job_id = parse_int(command.args)
        if job_id is None:
            await message.answer("Формат: /cancel_scheduled id")
            return
        if await storage.cancel_scheduled_job(job_id):
            await message.answer(f"Задание <code>{job_id}</code> отменено.")
        else:
            await message.answer("Не нашел активное задание с таким ID.")


async def execute_due_job(bot: Bot, storage: EventStorage, job: dict) -> None:
    job_id = int(job["id"])
    if not await storage.mark_job_processing(job_id):
        return

    try:
        payload = payload_from_job(job)
        if job["job_type"] == "channel_post":
            target_chat_id = chat_id_from_string(job["target_chat_id"])
            sent_messages = await send_payload_to_chat(bot, target_chat_id, payload)
            first_message_id = sent_messages[0].message_id if sent_messages else None
            await storage.mark_job_sent(job_id, telegram_message_id=first_message_id)
            return
        if job["job_type"] == "broadcast":
            result = await send_broadcast(bot, storage, payload)
            await storage.mark_job_sent(job_id)
            await storage.add_event(
                int(job["created_by"]),
                "scheduled_broadcast_sent",
                {"job_id": job_id, "payload_kind": payload["kind"], **result},
            )
            return
        await storage.mark_job_failed(job_id, f"Unknown job_type: {job['job_type']}")
    except Exception as exc:  # noqa: BLE001 - job executor must persist any failure.
        await storage.mark_job_failed(job_id, str(exc))


async def execute_media_group_caption_action(
    *,
    message: Message,
    bot: Bot,
    storage: EventStorage,
    settings: Settings,
    action: str,
    caption: Optional[str],
    admin_id: int,
    media_group_id: str,
) -> None:
    await asyncio.sleep(2)
    cached_items = await storage.admin_media_group(
        admin_id=admin_id,
        media_group_id=media_group_id,
    )
    photo_items = [
        item
        for item in sorted(cached_items, key=lambda item: int(item["message_id"]))
        if item["media_type"] == "photo"
    ]
    if not photo_items:
        await message.answer("Не удалось собрать альбом для отправки.")
        return
    if len(photo_items) == 1:
        payload: Payload = {
            "kind": "photo",
            "file_id": photo_items[0]["file_id"],
            "caption": caption,
        }
    else:
        payload = {
            "kind": "media_group",
            "items": [
                {
                    "type": "photo",
                    "file_id": item["file_id"],
                    "caption": caption if index == 0 else None,
                }
                for index, item in enumerate(photo_items)
            ],
        }
    await execute_direct_media_action(
        message=message,
        bot=bot,
        storage=storage,
        settings=settings,
        action=action,
        payload=payload,
    )


async def execute_direct_media_action(
    *,
    message: Message,
    bot: Bot,
    storage: EventStorage,
    settings: Settings,
    action: str,
    payload: Payload,
) -> None:
    if message.from_user is None:
        return
    if action == "post":
        channel_id = require_channel_id(settings)
        if channel_id is None:
            await message.answer("Не задан TELEGRAM_CHANNEL_ID.")
            return
        sent_messages = await send_payload_to_chat(bot, channel_id, payload)
        first_message_id = sent_messages[0].message_id if sent_messages else None
        await storage.add_event(
            message.from_user.id,
            "admin_channel_post_sent",
            {
                "message_id": first_message_id,
                "payload_kind": payload["kind"],
                "direct_caption_command": True,
            },
        )
        await message.answer(
            "Пост опубликован. "
            f"Message ID: <code>{first_message_id}</code>"
        )
        return

    if action == "broadcast":
        result = await send_broadcast(bot, storage, payload)
        await storage.add_event(
            message.from_user.id,
            "admin_broadcast_sent",
            {
                "payload_kind": payload["kind"],
                "direct_caption_command": True,
                **result,
            },
        )
        await message.answer(format_broadcast_result(result))
        return

    await message.answer("Для caption поддерживаются команды /post и /broadcast.")


async def build_message_payload(
    message: Message,
    storage: EventStorage,
    text: Optional[str],
) -> Optional[Payload]:
    clean_text = parse_required_text(text)
    if message.reply_to_message is not None and message.from_user is not None:
        media_payload = await payload_from_media_message(
            message.reply_to_message,
            storage,
            message.from_user.id,
            clean_text,
        )
        if media_payload is not None:
            return media_payload
    if clean_text is None:
        return None
    return {"kind": "text", "text": clean_text}


async def payload_from_media_message(
    message: Message,
    storage: EventStorage,
    admin_id: int,
    caption_override: Optional[str],
) -> Optional[Payload]:
    media = media_from_message(message)
    if media is None:
        return None

    caption = caption_override if caption_override is not None else parse_required_text(message.caption)
    if media["kind"] == "photo" and message.media_group_id:
        cached_items = await storage.admin_media_group(
            admin_id=admin_id,
            media_group_id=message.media_group_id,
        )
        if not cached_items:
            cached_items = []
        if not any(item["file_id"] == media["file_id"] for item in cached_items):
            cached_items.append(
                {
                    "media_type": media["kind"],
                    "file_id": media["file_id"],
                    "caption": message.caption,
                    "message_id": message.message_id,
                }
            )
        photo_items = [
            item
            for item in sorted(cached_items, key=lambda item: int(item["message_id"]))
            if item["media_type"] == "photo"
        ]
        if len(photo_items) > 1:
            album_caption = caption
            if album_caption is None:
                album_caption = next(
                    (parse_required_text(item.get("caption")) for item in photo_items if item.get("caption")),
                    None,
                )
            return {
                "kind": "media_group",
                "items": [
                    {
                        "type": "photo",
                        "file_id": item["file_id"],
                        "caption": album_caption if index == 0 else None,
                    }
                    for index, item in enumerate(photo_items)
                ],
            }

    return {
        "kind": media["kind"],
        "file_id": media["file_id"],
        "caption": caption,
    }


def media_from_message(message: Message) -> Optional[Payload]:
    if message.photo:
        return {"kind": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"kind": "video", "file_id": message.video.file_id}
    if message.document:
        return {"kind": "document", "file_id": message.document.file_id}
    return None


async def send_broadcast(bot: Bot, storage: EventStorage, payload: str | Payload) -> dict[str, int]:
    normalized_payload = normalize_payload(payload)
    sent = 0
    failed = 0
    blocked = 0
    for telegram_id in await storage.active_user_ids():
        try:
            await send_payload_to_chat(bot, telegram_id, normalized_payload)
            sent += 1
        except TelegramForbiddenError as exc:
            blocked += 1
            failed += 1
            await storage.mark_delivery_failed(telegram_id, str(exc))
        except TelegramBadRequest:
            failed += 1
    return {"sent": sent, "failed": failed, "blocked": blocked}


async def send_payload_to_chat(
    bot: Bot,
    chat_id: str | int,
    payload: str | Payload,
) -> list[Message]:
    normalized_payload = normalize_payload(payload)
    kind = normalized_payload["kind"]
    if kind == "text":
        sent = await bot.send_message(chat_id, normalized_payload["text"])
        return [sent]
    if kind == "photo":
        sent = await bot.send_photo(
            chat_id,
            photo=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
        )
        return [sent]
    if kind == "video":
        sent = await bot.send_video(
            chat_id,
            video=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
        )
        return [sent]
    if kind == "document":
        sent = await bot.send_document(
            chat_id,
            document=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
        )
        return [sent]
    if kind == "media_group":
        media = [
            InputMediaPhoto(media=item["file_id"], caption=item.get("caption"))
            for item in normalized_payload["items"]
        ]
        return await bot.send_media_group(chat_id, media=media)
    raise ValueError(f"Unsupported payload kind: {kind}")


def normalize_payload(payload: str | Payload) -> Payload:
    if isinstance(payload, str):
        return {"kind": "text", "text": payload}
    return payload


def payload_from_job(job: dict[str, Any]) -> Payload:
    raw_payload = job.get("payload")
    if raw_payload:
        try:
            loaded = json.loads(raw_payload)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict) and loaded.get("kind"):
            return loaded
    return {"kind": "text", "text": job["text"]}


def payload_preview(payload: str | Payload) -> str:
    normalized_payload = normalize_payload(payload)
    kind = normalized_payload["kind"]
    if kind == "text":
        return normalized_payload["text"]
    caption = parse_required_text(normalized_payload.get("caption"))
    if kind == "photo":
        return f"[photo] {caption or ''}".strip()
    if kind == "video":
        return f"[video] {caption or ''}".strip()
    if kind == "document":
        return f"[document/PDF] {caption or ''}".strip()
    if kind == "media_group":
        items = normalized_payload.get("items", [])
        first_caption = None
        if items:
            first_caption = parse_required_text(items[0].get("caption"))
        return f"[photo album: {len(items)}] {first_caption or ''}".strip()
    return f"[{kind}]"


def require_channel_id(settings: Settings) -> Optional[str | int]:
    if settings.telegram_channel_id is None:
        return None
    value = settings.telegram_channel_id
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def chat_id_from_string(value: str) -> str | int:
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def parse_required_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_media_caption_command(value: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
    if not value:
        return None
    parts = value.strip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/"):
        return None
    command = parts[0][1:].split("@", 1)[0].lower()
    if command not in {"post", "broadcast"}:
        return None
    text = parse_required_text(parts[1] if len(parts) > 1 else None)
    return command, text


def parse_scheduled_command(value: Optional[str]) -> Optional[tuple[datetime, Optional[str]]]:
    if not value:
        return None
    if "|" in value:
        date_part, text_part = value.split("|", 1)
        text = parse_required_text(text_part)
    else:
        date_part = value
        text = None
    try:
        local_dt = datetime.strptime(date_part.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return local_dt.replace(tzinfo=local_timezone()).astimezone(timezone.utc), text


def parse_scheduled_text(value: Optional[str]) -> Optional[tuple[datetime, str]]:
    parsed = parse_scheduled_command(value)
    if parsed is None:
        return None
    scheduled_at, text = parsed
    if text is None:
        return None
    return scheduled_at, text


def format_broadcast_result(result: dict[str, int]) -> str:
    return (
        "Рассылка завершена.\n"
        f"Отправлено: <b>{result['sent']}</b>\n"
        f"Ошибок: <b>{result['failed']}</b>\n"
        f"Заблокировали бота: <b>{result['blocked']}</b>"
    )


def local_timezone() -> tzinfo:
    for timezone_name in ("Europe/Kyiv", "Europe/Kiev"):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            continue
    return timezone(timedelta(hours=3), name="Europe/Kyiv")
