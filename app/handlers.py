import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message, ReplyKeyboardRemove

from app import content
from app.admin import admin_commands, is_admin
from app.config import Settings
from app.keyboards import contact_keyboard, discord_url_keyboard
from app.storage import EventStorage


router = Router()
admin_commands(router)
known_contact_user_ids: set[int] = set()
logger = logging.getLogger(__name__)


async def has_contact_access(storage: EventStorage, user_id: int) -> bool:
    if user_id in known_contact_user_ids:
        return True
    if await storage.user_has_contact(user_id):
        known_contact_user_ids.add(user_id)
        return True
    return False


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    await storage.record_start(message.from_user, command.args)
    if await has_contact_access(storage, message.from_user.id):
        await storage.mark_discord_access_sent(message.from_user)
        await message.answer(
            "Контакт уже сохранен. Повторно делиться номером не нужно.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            content.DISCORD_LINK_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
        return

    await message.answer(content.START_MESSAGE, reply_markup=contact_keyboard())


@router.message(Command("help"))
async def handle_help(message: Message, storage: EventStorage) -> None:
    if message.from_user is not None:
        await storage.record_message_interaction(message.from_user, "help_requested")
    await message.answer(content.HELP_MESSAGE)


@router.message(F.contact)
async def handle_contact(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None or message.contact is None:
        return

    if message.contact.user_id != message.from_user.id:
        await storage.ensure_user(message.from_user)
        await storage.add_event(message.from_user.id, "contact_rejected_not_own")
        await message.answer(content.CONTACT_NOT_OWN_MESSAGE, reply_markup=contact_keyboard())
        return

    await storage.save_contact(message.from_user, message.contact)
    known_contact_user_ids.add(message.from_user.id)
    await storage.mark_discord_access_sent(message.from_user)
    await message.answer(
        content.CONTACT_RECEIVED_MESSAGE,
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        content.DISCORD_LINK_MESSAGE,
        reply_markup=discord_url_keyboard(settings.discord_invite_url),
    )


@router.message()
async def handle_fallback(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
        await message.answer(content.CONTACT_REQUIRED_MESSAGE, reply_markup=contact_keyboard())
        return

    has_contact = await has_contact_access(storage, message.from_user.id)
    admin = is_admin(message, settings)
    logger.info(
        "Fallback decision user_id=%s username=%s admin=%s has_contact=%s text=%r",
        message.from_user.id,
        message.from_user.username,
        admin,
        has_contact,
        message.text,
    )

    await storage.record_message_interaction(
        message.from_user,
        "fallback_message",
        {
            "content_type": str(message.content_type),
            "has_text": bool(message.text),
            "text_length": len(message.text or ""),
        },
    )

    if admin:
        await message.answer(
            "Не понял команду. Для постов используй <code>new post</code> или <code>/newpost</code>."
        )
        return

    if has_contact:
        await message.answer(
            content.DISCORD_LINK_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
        return

    await message.answer(content.CONTACT_REQUIRED_MESSAGE, reply_markup=contact_keyboard())
