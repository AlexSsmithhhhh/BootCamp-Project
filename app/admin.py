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
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message

from app.config import Settings
from app.storage import EventStorage


Payload = dict[str, Any]
ADMIN_POST_CONFIRM_CALLBACK = "admin_post_confirm"
ADMIN_POST_EDIT_CALLBACK = "admin_post_edit"
ADMIN_POST_CANCEL_CALLBACK = "admin_post_cancel"
ADMIN_POST_SKIP_BUTTONS_CALLBACK = "admin_post_skip_buttons"
ADMIN_POST_NOW_CALLBACK = "admin_post_now"
ADMIN_POST_BROADCAST_CALLBACK = "admin_post_broadcast"
ADMIN_POST_SCHEDULE_CALLBACK = "admin_post_schedule"
ADMIN_MANAGE_DELETE_PREFIX = "admin_manage_delete:"
BROADCAST_NOW_MODES = {"broadcast_now", "now"}
BROADCAST_SCHEDULED_MODES = {"broadcast_scheduled", "scheduled"}
MAX_LINK_BUTTONS = 100


class AdminOnly(BaseFilter):
    async def __call__(self, message: Message, settings: Settings) -> bool:
        return is_admin(message, settings)


class TextCommand(BaseFilter):
    def __init__(self, name: str) -> None:
        self.name = name

    async def __call__(self, message: Message) -> bool:
        normalized = normalize_plain_command(message.text)
        return normalized == self.name


class TextCommandStartsWith(BaseFilter):
    def __init__(self, name: str) -> None:
        self.name = name

    async def __call__(self, message: Message) -> bool:
        normalized = normalize_plain_command(message.text)
        return bool(normalized and normalized.startswith(f"{self.name} "))


def is_admin(message: Message, settings: Settings) -> bool:
    if message.from_user is None:
        return False
    return is_admin_identity(
        user_id=message.from_user.id,
        username=message.from_user.username,
        settings=settings,
    )


def is_admin_identity(user_id: int, username: Optional[str], settings: Settings) -> bool:
    if user_id in settings.telegram_admin_ids:
        return True
    if username is None:
        return False
    return username.lower() in settings.telegram_admin_usernames


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

        draft = await storage.admin_post_draft(message.from_user.id)
        if draft and draft["status"] in {"awaiting_content", "processing_album"}:
            if message.media_group_id and media["kind"] == "photo":
                if draft["status"] == "awaiting_content":
                    await storage.save_admin_post_draft(
                        admin_id=message.from_user.id,
                        mode=draft["mode"],
                        status="processing_album",
                        scheduled_at=parse_stored_datetime(draft.get("scheduled_at")),
                        media_group_id=message.media_group_id,
                    )
                    asyncio.create_task(
                        execute_draft_media_group_action(
                            message=message,
                            bot=bot,
                            storage=storage,
                            settings=settings,
                            admin_id=message.from_user.id,
                            media_group_id=message.media_group_id,
                        )
                    )
                return

            payload = {
                "kind": media["kind"],
                "file_id": media["file_id"],
                "caption": parse_required_text(message.caption),
            }
            await finish_admin_post_draft(
                message=message,
                bot=bot,
                storage=storage,
                settings=settings,
                draft=draft,
                payload=payload,
            )
            return

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
                    "/post - мастер: пост всем сейчас, рассылка по сегментам или запланировать",
                    "/drop_post или /new_post - старые алиасы мастера /post",
                    "/manage - управлять запланированными отправками",
                    "/admin - аналитика пользователей и источников",
                    "/all_post или all post - все запланированные посты",
                    "/delete ID или delete ID - отменить запланированный пост",
                    "/analytics или analytics - аналитика Telegram-бота",
                    "/post текст - создать preview и отправить пользователям бота после подтверждения",
                    "/post ответом на фото/альбом/видео/PDF создает preview этого медиа для отправки пользователям",
                    "Фото/видео/PDF с caption `/post текст` тоже идет через preview",
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

    @router.message(Command("drop_post", "new_post", "newpost"))
    @router.message(TextCommand("drop post"))
    @router.message(TextCommand("дроп пост"))
    @router.message(TextCommand("new post"))
    @router.message(F.text.regexp(r"^\s*/?(drop_?post|new_?post|дроп_?пост)(?:@\w+)?\s*$"))
    async def handle_new_post(message: Message, storage: EventStorage, settings: Settings) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await start_admin_post_wizard(message, storage, settings)

    @router.callback_query(
        F.data.in_(
            {
                ADMIN_POST_NOW_CALLBACK,
                ADMIN_POST_BROADCAST_CALLBACK,
                ADMIN_POST_SCHEDULE_CALLBACK,
            }
        )
    )
    async def handle_new_post_choice(
        callback: CallbackQuery,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin_identity(callback.from_user.id, callback.from_user.username, settings):
            await callback.answer("Доступно только администратору.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer("Не могу продолжить здесь.", show_alert=True)
            return

        if callback.data == ADMIN_POST_BROADCAST_CALLBACK:
            await callback.message.answer(
                "Рассылка по сегментам пока зарезервирована под будущие теги и сегменты.\n\n"
                "Сейчас для отправки всем активным пользователям выбери <b>Пост всем сейчас</b>. "
                "Когда добавим сегменты, здесь будет выбор аудитории перед контентом и preview."
            )
            await callback.answer()
            return

        if callback.data == ADMIN_POST_NOW_CALLBACK:
            await storage.save_admin_post_draft(
                admin_id=callback.from_user.id,
                mode="broadcast_now",
                status="awaiting_content",
            )
            await callback.message.answer(
                "Ок, готовим пост всем активным пользователям бота.\n\n"
                "Отправь следующим сообщением текст, фото, альбом, видео или PDF. "
                "Я покажу предпросмотр и попрошу подтвердить перед отправкой."
            )
            await callback.answer()
            return

        await storage.save_admin_post_draft(
            admin_id=callback.from_user.id,
            mode="broadcast_scheduled",
            status="awaiting_schedule",
        )
        await callback.message.answer(
            "Укажи дату и время отправки по Киеву в формате <code>YYYY-MM-DD HH:MM</code>.\n"
            "Например: <code>2026-05-20 14:00</code>"
        )
        await callback.answer()

    @router.callback_query(
        F.data.in_(
            {
                ADMIN_POST_CONFIRM_CALLBACK,
                ADMIN_POST_EDIT_CALLBACK,
                ADMIN_POST_CANCEL_CALLBACK,
                ADMIN_POST_SKIP_BUTTONS_CALLBACK,
            }
        )
    )
    async def handle_admin_post_confirmation(
        callback: CallbackQuery,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin_identity(callback.from_user.id, callback.from_user.username, settings):
            await callback.answer("Доступно только администратору.", show_alert=True)
            return
        if callback.message is None:
            await callback.answer("Не могу продолжить здесь.", show_alert=True)
            return

        if callback.data == ADMIN_POST_CANCEL_CALLBACK:
            await clear_callback_keyboard(callback.message)
            await storage.clear_admin_post_draft(callback.from_user.id)
            await callback.message.answer("Публикация отменена.")
            await callback.answer()
            return

        if callback.data == ADMIN_POST_SKIP_BUTTONS_CALLBACK:
            draft = await storage.admin_post_draft(callback.from_user.id)
            payload = payload_from_draft(draft) if draft else None
            if draft is None or payload is None:
                await clear_callback_keyboard(callback.message)
                await callback.message.answer("Активного черновика нет. Начни заново: /post")
                await callback.answer()
                return
            await clear_callback_keyboard(callback.message)
            await save_admin_post_preview(
                message=callback.message,
                storage=storage,
                draft=draft,
                payload=payload,
                admin_id=callback.from_user.id,
            )
            await callback.answer()
            return

        if callback.data == ADMIN_POST_EDIT_CALLBACK:
            await clear_callback_keyboard(callback.message)
            await callback.message.answer(
                "Редактирование убрали из flow. Если нужно изменить пост, отмени и начни заново: /post"
            )
            await callback.answer()
            return

        await clear_callback_keyboard(callback.message)
        await confirm_admin_post_draft(
            responder=callback.message,
            bot=bot,
            storage=storage,
            settings=settings,
            admin_id=callback.from_user.id,
        )
        await callback.answer()

    @router.message(Command("all_post"))
    @router.message(TextCommand("all post"))
    @router.message(F.text.regexp(r"^\s*/?all_?post(?:@\w+)?\s*$"))
    async def handle_all_post(message: Message, storage: EventStorage, settings: Settings) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await send_scheduled_jobs(message, storage)

    @router.message(Command("manage"))
    @router.message(TextCommand("manage"))
    @router.message(F.text.regexp(r"^\s*/?manage(?:@\w+)?\s*$"))
    async def handle_manage(message: Message, storage: EventStorage, settings: Settings) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await send_manage_jobs(message, storage)

    @router.callback_query(F.data.regexp(r"^admin_manage_delete:\d+$"))
    async def handle_manage_delete(
        callback: CallbackQuery,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin_identity(callback.from_user.id, callback.from_user.username, settings):
            await callback.answer("Доступно только администратору.", show_alert=True)
            return
        if callback.message is None or callback.data is None:
            await callback.answer("Не могу продолжить здесь.", show_alert=True)
            return
        job_id = parse_int(callback.data.removeprefix(ADMIN_MANAGE_DELETE_PREFIX))
        if job_id is None:
            await callback.answer("Не понял ID.", show_alert=True)
            return
        if await storage.cancel_scheduled_job(job_id):
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.message.answer(f"Задание <code>{job_id}</code> удалено.")
            await send_manage_jobs(callback.message, storage)
            await callback.answer()
            return
        await callback.answer("Задание уже не активно или не найдено.", show_alert=True)

    @router.message(Command("delete"))
    async def handle_delete_command(
        message: Message,
        command: CommandObject,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await delete_scheduled_job_from_text(message, storage, command.args)

    @router.message(TextCommandStartsWith("delete"))
    async def handle_delete_text(
        message: Message,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        await delete_scheduled_job_from_text(
            message,
            storage,
            normalize_plain_command(message.text).split(maxsplit=1)[1],
        )

    @router.message(Command("admin"))
    @router.message(TextCommand("admin"))
    @router.message(F.text.regexp(r"^\s*/?admin(?:@\w+)?\s*$"))
    @router.message(Command("analytics"))
    @router.message(TextCommand("analytics"))
    @router.message(F.text.regexp(r"^\s*/?analytics(?:@\w+)?\s*$"))
    async def handle_admin_dashboard(
        message: Message,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        overview = await storage.analytics_overview()
        sources = await storage.analytics_sources(limit=10)
        await message.answer(format_analytics(overview, sources))

    @router.message(Command("post"))
    async def handle_post(
        message: Message,
        command: CommandObject,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if not is_admin(message, settings):
            await deny_non_admin(message)
            return
        payload = await build_message_payload(message, storage, command.args)
        if payload is None:
            await start_admin_post_wizard(message, storage, settings)
            return
        await start_admin_post_preview_from_payload(
            message=message,
            storage=storage,
            settings=settings,
            payload=payload,
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
            await send_missing_channel_setup(message)
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
            await send_missing_channel_setup(message)
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
        await send_scheduled_jobs(message, storage)

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

    @router.message(AdminOnly())
    async def handle_admin_post_draft_message(
        message: Message,
        bot: Bot,
        storage: EventStorage,
        settings: Settings,
    ) -> None:
        if message.from_user is None:
            return
        draft = await storage.admin_post_draft(message.from_user.id)
        if draft is None:
            return

        if draft["status"] == "awaiting_schedule":
            scheduled_at = parse_post_schedule_input(message.text)
            if scheduled_at is None:
                await message.answer(
                    "Не понял дату. Напиши в формате YYYY-MM-DD HH:MM.\n"
                    "Например: 2026-05-20 14:00"
                )
                return
            await storage.save_admin_post_draft(
                admin_id=message.from_user.id,
                mode=draft["mode"],
                status="awaiting_content",
                scheduled_at=scheduled_at,
            )
            await message.answer(
                "Время сохранил. Теперь отправь текст, фото, альбом, видео или PDF. "
                "Если это медиа, текст добавь прямо в подпись."
            )
            return

        if draft["status"] == "awaiting_content" and message.text:
            await finish_admin_post_draft(
                message=message,
                bot=bot,
                storage=storage,
                settings=settings,
                draft=draft,
                payload={"kind": "text", "text": message.text.strip()},
            )
            return

        if draft["status"] == "awaiting_buttons":
            payload = payload_from_draft(draft)
            if payload is None:
                await message.answer("Не нашел контент черновика. Начни заново: /post")
                await storage.clear_admin_post_draft(message.from_user.id)
                return
            parsed_buttons = parse_link_buttons_input(message.text)
            if parsed_buttons["error"]:
                await message.answer(parsed_buttons["error"])
                return
            payload = payload_with_buttons(payload, parsed_buttons["buttons"])
            await save_admin_post_preview(
                message=message,
                storage=storage,
                draft=draft,
                payload=payload,
            )
            return

        if draft["status"] == "awaiting_confirm":
            await message.answer(
                "Черновик уже готов. Используй кнопки под предпросмотром: "
                "отправить/запланировать или отменить."
            )


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


def new_post_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пост всем сейчас",
                    callback_data=ADMIN_POST_NOW_CALLBACK,
                ),
                InlineKeyboardButton(
                    text="Рассылка по сегментам",
                    callback_data=ADMIN_POST_BROADCAST_CALLBACK,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Запланировать",
                    callback_data=ADMIN_POST_SCHEDULE_CALLBACK,
                ),
            ]
        ]
    )


def admin_post_preview_keyboard(mode: str) -> InlineKeyboardMarkup:
    confirm_text = "Отправить" if mode in BROADCAST_NOW_MODES else "Запланировать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=confirm_text,
                    callback_data=ADMIN_POST_CONFIRM_CALLBACK,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=ADMIN_POST_CANCEL_CALLBACK,
                )
            ],
        ]
    )


def admin_post_buttons_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без кнопок",
                    callback_data=ADMIN_POST_SKIP_BUTTONS_CALLBACK,
                )
            ]
        ]
    )


async def clear_callback_keyboard(message: Message) -> None:
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


def link_buttons_keyboard(buttons: list[dict[str, str]]) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button["text"], url=button["url"])]
            for button in buttons
        ]
    )


def missing_channel_setup_message() -> str:
    return "\n".join(
        [
            "<b>Канал для публикаций не настроен</b>",
            "",
            "Чтобы публиковать посты, нужно:",
            "1. Создать или открыть Telegram-канал.",
            "2. Добавить <code>@bootcampweek_bot</code> администратором с правом публиковать.",
            "3. В Railway service <code>bootcamp-telegram-bot</code> добавить переменную:",
            "<code>TELEGRAM_CHANNEL_ID=@channel_username</code>",
            "",
            "Для приватного канала вместо username нужен id вида <code>-1001234567890</code>.",
        ]
    )


async def send_missing_channel_setup(message: Message) -> None:
    await message.answer(missing_channel_setup_message())


async def start_admin_post_wizard(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    await storage.ensure_user(message.from_user)
    await storage.save_admin_post_draft(
        admin_id=message.from_user.id,
        mode="choose",
        status="choosing",
    )
    await message.answer(
        "Запускаю мастер отправки.\n\n"
        "Выбери, что сделать: пост всем сейчас, рассылку по сегментам или запланировать отправку. "
        "Потом пришли текст, фото, альбом, видео или PDF. Перед отправкой я покажу предпросмотр.",
        reply_markup=new_post_keyboard(),
    )


async def start_admin_post_preview_from_payload(
    *,
    message: Message,
    storage: EventStorage,
    settings: Settings,
    payload: Payload,
) -> None:
    if message.from_user is None:
        return

    await storage.ensure_user(message.from_user)
    await ask_admin_post_buttons(
        message=message,
        storage=storage,
        draft={"mode": "broadcast_now"},
        payload=payload,
    )


async def send_scheduled_jobs(message: Message, storage: EventStorage) -> None:
    jobs = await storage.list_scheduled_jobs(limit=30)
    if not jobs:
        await message.answer("Запланированных постов нет.")
        return
    lines = ["<b>Запланированные публикации</b>"]
    for job in jobs:
        preview = escape(payload_preview(payload_from_job(job))[:120])
        lines.append(
            f"ID <code>{job['id']}</code> · {job['job_type']} · {job['scheduled_at']}\n{preview}"
        )
    await message.answer("\n\n".join(lines))


async def send_manage_jobs(message: Message, storage: EventStorage) -> None:
    jobs = await storage.list_scheduled_jobs(limit=30)
    if not jobs:
        await message.answer("Запланированных отправок нет.")
        return

    lines = ["<b>Управление запланированными отправками</b>"]
    keyboard_rows = []
    for job in jobs:
        preview = escape(payload_preview(payload_from_job(job))[:140])
        lines.append(
            f"ID <code>{job['id']}</code> · {job['job_type']} · {job['scheduled_at']}\n{preview}"
        )
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"Удалить {job['id']}",
                    callback_data=f"{ADMIN_MANAGE_DELETE_PREFIX}{job['id']}",
                )
            ]
        )

    await message.answer(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )


async def delete_scheduled_job_from_text(
    message: Message,
    storage: EventStorage,
    value: Optional[str],
) -> None:
    job_id = parse_int(value)
    if job_id is None:
        await message.answer("Формат: /delete ID или delete ID")
        return
    if await storage.cancel_scheduled_job(job_id):
        await message.answer(f"Запланированная публикация <code>{job_id}</code> отменена.")
    else:
        await message.answer("Не нашел активную запланированную публикацию с таким ID.")


def format_analytics(
    overview: dict[str, int],
    sources: Optional[list[dict[str, Any]]] = None,
) -> str:
    contacts_shared = overview["contacts_shared"]
    users_total = overview["users_total"]
    lines = [
        "<b>Admin analytics</b>",
        f"Всего пользователей: <b>{users_total}</b>",
        f"Активных: <b>{overview['users_active']}</b>",
        f"Заблокировали бота: <b>{overview['users_blocked']}</b>",
        f"Новых за 24 часа: <b>{overview.get('users_last_24h', 0)}</b>",
        f"Новых за 7 дней: <b>{overview.get('users_last_7d', 0)}</b>",
        f"Контактов получено: <b>{contacts_shared}</b> ({format_percent(contacts_shared, users_total)})",
        f"Контактов за 7 дней: <b>{overview.get('contacts_last_7d', 0)}</b>",
        f"Discord-инвайтов выдано: <b>{overview['discord_invites_sent']}</b>",
        f"Стартов всего: <b>{overview.get('starts_total', 0)}</b>",
        f"Событий в журнале: <b>{overview['events_total']}</b>",
    ]

    lines.append("")
    lines.append("<b>Источники / сегменты</b>")
    if sources:
        for source in sources:
            source_name = str(source.get("source") or "direct")
            source_users = int(source.get("users_total") or 0)
            source_contacts = int(source.get("contacts_shared") or 0)
            lines.append(
                f"{escape(source_name)}: <b>{source_users}</b> users, "
                f"{source_contacts} contacts ({format_percent(source_contacts, source_users)})"
            )
    else:
        lines.append("Пока нет данных по источникам.")

    lines.extend(
        [
            "",
            "<b>Как трекать ссылки</b>",
            "Используй deep-link payload после <code>?start=</code>:",
            "<code>https://t.me/&lt;bot_username&gt;?start=instagram</code>",
            "<code>https://t.me/&lt;bot_username&gt;?start=utm_source_instagram</code>",
            "Бот сохранит сегмент при первом /start и покажет его здесь.",
        ]
    )
    return "\n".join(lines)


def format_percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{part * 100 / total:.0f}%"


def payload_from_draft(draft: dict[str, Any]) -> Optional[Payload]:
    raw_payload = draft.get("payload")
    if not raw_payload:
        return None
    try:
        loaded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict) and loaded.get("kind"):
        return loaded
    return None


def payload_buttons(payload: str | Payload) -> list[dict[str, str]]:
    normalized_payload = normalize_payload(payload)
    buttons = normalized_payload.get("buttons")
    if not isinstance(buttons, list):
        return []
    normalized_buttons = []
    for button in buttons:
        if not isinstance(button, dict):
            continue
        raw_text = button.get("text")
        raw_url = button.get("url")
        if not isinstance(raw_text, str) or not isinstance(raw_url, str):
            continue
        text = parse_required_text(raw_text)
        url = parse_required_text(raw_url)
        if text and url:
            normalized_buttons.append({"text": text, "url": url})
    return normalized_buttons


def payload_with_buttons(payload: Payload, buttons: list[dict[str, str]]) -> Payload:
    updated_payload = dict(payload)
    if buttons:
        updated_payload["buttons"] = buttons
    else:
        updated_payload.pop("buttons", None)
    return updated_payload


def format_admin_post_preview(draft: dict[str, Any], payload: Payload) -> str:
    mode = "сейчас" if draft["mode"] in BROADCAST_NOW_MODES else "запланировано"
    lines = [
        "<b>Предпросмотр сообщения</b>",
        f"Режим: <b>{mode}</b>",
        "Получатели: <b>активные пользователи бота</b>",
    ]
    if draft["mode"] in BROADCAST_SCHEDULED_MODES and draft.get("scheduled_at"):
        lines.append(f"Время: <code>{escape(str(draft['scheduled_at']))}</code>")
    lines.extend(
        [
            "",
            "<b>Контент</b>",
            escape(payload_preview(payload)[:1200]),
            "",
            "<b>Кнопки</b>",
            format_link_buttons_preview(payload_buttons(payload)),
            "",
            "Проверь сообщение и выбери действие ниже.",
        ]
    )
    return "\n".join(lines)


async def save_admin_post_preview(
    *,
    message: Message,
    storage: EventStorage,
    draft: dict[str, Any],
    payload: Payload,
    admin_id: Optional[int] = None,
) -> None:
    target_admin_id = admin_id
    if target_admin_id is None and message.from_user is not None:
        target_admin_id = message.from_user.id
    if target_admin_id is None:
        return

    scheduled_at = parse_stored_datetime(draft.get("scheduled_at"))
    if draft["mode"] in BROADCAST_SCHEDULED_MODES and scheduled_at is None:
        await message.answer("Не нашел время отправки. Начни заново: /post")
        await storage.clear_admin_post_draft(target_admin_id)
        return

    await storage.save_admin_post_draft(
        admin_id=target_admin_id,
        mode=draft["mode"],
        status="awaiting_confirm",
        scheduled_at=scheduled_at,
        media_group_id=draft.get("media_group_id"),
        payload=payload,
    )
    preview_draft = await storage.admin_post_draft(target_admin_id)
    if preview_draft is None:
        preview_draft = draft | {"status": "awaiting_confirm"}
    await message.answer(
        format_admin_post_preview(preview_draft, payload),
        reply_markup=admin_post_preview_keyboard(draft["mode"]),
    )


async def ask_admin_post_buttons(
    *,
    message: Message,
    storage: EventStorage,
    draft: dict[str, Any],
    payload: Payload,
) -> None:
    if message.from_user is None:
        return
    scheduled_at = parse_stored_datetime(draft.get("scheduled_at"))
    await storage.save_admin_post_draft(
        admin_id=message.from_user.id,
        mode=draft["mode"],
        status="awaiting_buttons",
        scheduled_at=scheduled_at,
        media_group_id=draft.get("media_group_id"),
        payload=payload,
    )
    await message.answer(
        "Кнопки под постом нужны?\n\n"
        "Если да, пришли каждую кнопку с новой строки в формате:\n"
        "<code>Текст кнопки | https://example.com</code>\n\n"
        f"Можно добавить до {MAX_LINK_BUTTONS} кнопок. Если кнопки не нужны, нажми <b>Без кнопок</b>.",
        reply_markup=admin_post_buttons_keyboard(),
    )


async def confirm_admin_post_draft(
    *,
    responder: Message,
    bot: Bot,
    storage: EventStorage,
    settings: Settings,
    admin_id: int,
) -> None:
    draft = await storage.admin_post_draft(admin_id)
    if draft is None or draft["status"] != "awaiting_confirm":
        await responder.answer("Активного черновика нет. Начни заново: /post")
        return

    payload = payload_from_draft(draft)
    if payload is None:
        await responder.answer("Не нашел контент черновика. Начни заново: /post")
        await storage.clear_admin_post_draft(admin_id)
        return

    if draft["mode"] in BROADCAST_NOW_MODES:
        result = await send_broadcast(bot, storage, payload)
        await storage.add_event(
            admin_id,
            "admin_broadcast_sent",
            {
                "payload_kind": payload["kind"],
                "post_wizard": True,
                **result,
            },
        )
        await storage.clear_admin_post_draft(admin_id)
        await responder.answer(format_broadcast_result(result))
        return

    if draft["mode"] in BROADCAST_SCHEDULED_MODES:
        scheduled_at = parse_stored_datetime(draft.get("scheduled_at"))
        if scheduled_at is None:
            await responder.answer("Не нашел время отправки. Начни заново: /post")
            await storage.clear_admin_post_draft(admin_id)
            return
        job_id = await storage.create_scheduled_job(
            job_type="broadcast",
            text=payload_preview(payload),
            payload=payload,
            scheduled_at=scheduled_at,
            created_by=admin_id,
        )
        await storage.clear_admin_post_draft(admin_id)
        await responder.answer(f"Рассылка запланирована. ID: <code>{job_id}</code>")
        return

    await responder.answer("Не понял режим отправки. Начни заново: /post")
    await storage.clear_admin_post_draft(admin_id)


async def execute_draft_media_group_action(
    *,
    message: Message,
    bot: Bot,
    storage: EventStorage,
    settings: Settings,
    admin_id: int,
    media_group_id: str,
) -> None:
    await asyncio.sleep(2)
    draft = await storage.admin_post_draft(admin_id)
    if not draft or draft["status"] != "processing_album":
        return
    if draft.get("media_group_id") != media_group_id:
        return

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
        await storage.clear_admin_post_draft(admin_id)
        return

    caption = next(
        (parse_required_text(item.get("caption")) for item in photo_items if item.get("caption")),
        None,
    )
    payload: Payload
    if len(photo_items) == 1:
        payload = {
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
    await finish_admin_post_draft(
        message=message,
        bot=bot,
        storage=storage,
        settings=settings,
        draft=draft,
        payload=payload,
    )


async def finish_admin_post_draft(
    *,
    message: Message,
    bot: Bot,
    storage: EventStorage,
    settings: Settings,
    draft: dict[str, Any],
    payload: Payload,
) -> None:
    if message.from_user is None:
        return
    if draft["mode"] in BROADCAST_NOW_MODES | BROADCAST_SCHEDULED_MODES:
        await ask_admin_post_buttons(
            message=message,
            storage=storage,
            draft=draft,
            payload=payload,
        )
        return

    await message.answer("Не понял режим отправки. Начни заново: /post")
    await storage.clear_admin_post_draft(message.from_user.id)


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
        await start_admin_post_preview_from_payload(
            message=message,
            storage=storage,
            settings=settings,
            payload=payload,
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
    buttons = payload_buttons(normalized_payload)
    reply_markup = link_buttons_keyboard(buttons)
    if kind == "text":
        sent = await bot.send_message(chat_id, normalized_payload["text"], reply_markup=reply_markup)
        return [sent]
    if kind == "photo":
        sent = await bot.send_photo(
            chat_id,
            photo=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
            reply_markup=reply_markup,
        )
        return [sent]
    if kind == "video":
        sent = await bot.send_video(
            chat_id,
            video=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
            reply_markup=reply_markup,
        )
        return [sent]
    if kind == "document":
        sent = await bot.send_document(
            chat_id,
            document=normalized_payload["file_id"],
            caption=normalized_payload.get("caption"),
            reply_markup=reply_markup,
        )
        return [sent]
    if kind == "media_group":
        media = [
            InputMediaPhoto(media=item["file_id"], caption=item.get("caption"))
            for item in normalized_payload["items"]
        ]
        sent_messages = await bot.send_media_group(chat_id, media=media)
        if reply_markup is not None:
            link_message = await bot.send_message(chat_id, "Ссылки к посту:", reply_markup=reply_markup)
            sent_messages.append(link_message)
        return sent_messages
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


def format_link_buttons_preview(buttons: list[dict[str, str]]) -> str:
    if not buttons:
        return "без кнопок"
    return "\n".join(
        f"• {escape(button['text'])} → {escape(button['url'])}"
        for button in buttons
    )


def parse_link_buttons_input(value: Optional[str]) -> dict[str, Any]:
    text = parse_required_text(value)
    if text is None:
        return {"buttons": [], "error": button_input_help("Пришли кнопки текстом или нажми «Без кнопок».")}
    if text.lower() in {"без кнопок", "без", "нет", "no", "skip"}:
        return {"buttons": [], "error": None}

    buttons = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parsed = parse_link_button_line(line)
        if parsed is None:
            return {
                "buttons": [],
                "error": button_input_help(
                    f"Не понял кнопку в строке {line_number}: <code>{escape(line)}</code>"
                ),
            }
        buttons.append(parsed)

    if not buttons:
        return {"buttons": [], "error": button_input_help("Не нашел ни одной кнопки.")}
    if len(buttons) > MAX_LINK_BUTTONS:
        return {
            "buttons": [],
            "error": f"Слишком много кнопок. Максимум: {MAX_LINK_BUTTONS}.",
        }
    return {"buttons": buttons, "error": None}


def parse_link_button_line(line: str) -> Optional[dict[str, str]]:
    if "|" in line:
        label, url = line.split("|", 1)
        label = label.strip()
        url = url.strip()
    else:
        marker = "http://"
        index = line.find(marker)
        https_index = line.find("https://")
        if https_index >= 0 and (index < 0 or https_index < index):
            marker = "https://"
            index = https_index
        if index < 0:
            return None
        label = line[:index].strip(" -—|")
        url = line[index:].strip()

    if not label or not is_http_url(url) or any(char.isspace() for char in url):
        return None
    return {"text": label[:64], "url": url[:2048]}


def button_input_help(prefix: str) -> str:
    return (
        f"{prefix}\n\n"
        "Формат каждой строки:\n"
        "<code>Текст кнопки | https://example.com</code>"
    )


def is_http_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


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


def normalize_plain_command(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("/"):
        command, *rest = normalized.split(maxsplit=1)
        command = command[1:].split("@", 1)[0].replace("_", " ")
        normalized = command
        if rest:
            normalized = f"{normalized} {rest[0]}"
    if normalized.startswith("newpost"):
        normalized = normalized.replace("newpost", "new post", 1)
    if normalized.startswith("allpost"):
        normalized = normalized.replace("allpost", "all post", 1)
    if normalized.startswith("droppost"):
        normalized = normalized.replace("droppost", "drop post", 1)
    if normalized.startswith("дроппост"):
        normalized = normalized.replace("дроппост", "дроп пост", 1)
    return " ".join(normalized.split())


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


def parse_post_schedule_input(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        local_dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return local_dt.replace(tzinfo=local_timezone()).astimezone(timezone.utc)


def parse_stored_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
