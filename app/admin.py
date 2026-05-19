from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from html import escape
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config import Settings
from app.storage import EventStorage


def is_admin(message: Message, settings: Settings) -> bool:
    return bool(message.from_user and message.from_user.id in settings.telegram_admin_ids)


async def deny_non_admin(message: Message) -> None:
    await message.answer("Команда доступна только администратору.")


def admin_commands(router) -> None:
    @router.message(Command("admin_help"))
    async def handle_admin_help(message: Message, settings: Settings) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await message.answer(
            "\n".join(
                [
                    "<b>Admin-команды</b>",
                    "/post текст - сразу опубликовать пост в канал",
                    "/delete_post message_id - удалить пост из канала",
                    "/broadcast текст - сразу отправить рассылку всем активным пользователям",
                    "/schedule_post YYYY-MM-DD HH:MM | текст - запланировать пост",
                    "/schedule_broadcast YYYY-MM-DD HH:MM | текст - запланировать рассылку",
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
        text = parse_required_text(command.args)
        if text is None:
            await message.answer("Формат: /post текст поста")
            return
        sent = await bot.send_message(channel_id, text)
        await storage.add_event(
            message.from_user.id,
            "admin_channel_post_sent",
            {"message_id": sent.message_id},
        )
        await message.answer(f"Пост опубликован. Message ID: <code>{sent.message_id}</code>")

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
        text = parse_required_text(command.args)
        if text is None:
            await message.answer("Формат: /broadcast текст рассылки")
            return
        await storage.ensure_user(message.from_user)
        result = await send_broadcast(bot, storage, text)
        await storage.add_event(message.from_user.id, "admin_broadcast_sent", result)
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
        parsed = parse_scheduled_text(command.args)
        if parsed is None:
            await message.answer("Формат: /schedule_post YYYY-MM-DD HH:MM | текст поста")
            return
        scheduled_at, text = parsed
        job_id = await storage.create_scheduled_job(
            job_type="channel_post",
            text=text,
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
        parsed = parse_scheduled_text(command.args)
        if parsed is None:
            await message.answer("Формат: /schedule_broadcast YYYY-MM-DD HH:MM | текст рассылки")
            return
        await storage.ensure_user(message.from_user)
        scheduled_at, text = parsed
        job_id = await storage.create_scheduled_job(
            job_type="broadcast",
            text=text,
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
            text_preview = escape(job["text"][:80])
            lines.append(
                f"#{job['id']} · {job['job_type']} · {job['scheduled_at']}\n{text_preview}"
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
        if job["job_type"] == "channel_post":
            target_chat_id = chat_id_from_string(job["target_chat_id"])
            sent = await bot.send_message(target_chat_id, job["text"])
            await storage.mark_job_sent(job_id, telegram_message_id=sent.message_id)
            return
        if job["job_type"] == "broadcast":
            result = await send_broadcast(bot, storage, job["text"])
            await storage.mark_job_sent(job_id)
            await storage.add_event(
                int(job["created_by"]),
                "scheduled_broadcast_sent",
                {"job_id": job_id, **result},
            )
            return
        await storage.mark_job_failed(job_id, f"Unknown job_type: {job['job_type']}")
    except Exception as exc:  # noqa: BLE001 - job executor must persist any failure.
        await storage.mark_job_failed(job_id, str(exc))


async def send_broadcast(bot: Bot, storage: EventStorage, text: str) -> dict[str, int]:
    sent = 0
    failed = 0
    blocked = 0
    for telegram_id in await storage.active_user_ids():
        try:
            await bot.send_message(telegram_id, text)
            sent += 1
        except TelegramForbiddenError as exc:
            blocked += 1
            failed += 1
            await storage.mark_delivery_failed(telegram_id, str(exc))
        except TelegramBadRequest:
            failed += 1
    return {"sent": sent, "failed": failed, "blocked": blocked}


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


def parse_scheduled_text(value: Optional[str]) -> Optional[tuple[datetime, str]]:
    if not value or "|" not in value:
        return None
    date_part, text_part = value.split("|", 1)
    text = text_part.strip()
    if not text:
        return None
    try:
        local_dt = datetime.strptime(date_part.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return local_dt.replace(tzinfo=local_timezone()).astimezone(timezone.utc), text


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
