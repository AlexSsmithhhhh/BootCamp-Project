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
known_contact_user_ids: set[int] = set()
logger = logging.getLogger(__name__)
CONTACT_PROMPT_COOLDOWN_SECONDS = 6 * 60 * 60


async def has_contact_access(storage: EventStorage, user_id: int) -> bool:
    if user_id in known_contact_user_ids:
        logger.info("Contact access cache hit user_id=%s", user_id)
        return True
    has_contact = await storage.user_has_contact(user_id)
    logger.info("Contact access check user_id=%s result=%s", user_id, has_contact)
    if has_contact:
        known_contact_user_ids.add(user_id)
        return True
    return False


def is_command_text(message: Message) -> bool:
    text = (message.text or "").strip()
    return text.startswith("/")


def start_message_for_state(*, is_new_user: bool, has_contact: bool) -> str:
    if has_contact:
        return content.RETURNING_WITH_CONTACT_MESSAGE
    if is_new_user:
        return content.START_MESSAGE
    return content.RETURNING_WITHOUT_CONTACT_MESSAGE


async def send_contact_prompt(
    message: Message,
    storage: EventStorage,
    *,
    force: bool = False,
    quiet_if_recent: bool = False,
) -> None:
    if message.from_user is None:
        return

    should_prompt = force or await storage.should_prompt_contact(
        message.from_user.id,
        cooldown_seconds=CONTACT_PROMPT_COOLDOWN_SECONDS,
    )
    if should_prompt:
        await storage.mark_contact_prompted(message.from_user)
        await message.answer(content.CONTACT_REQUIRED_MESSAGE, reply_markup=contact_keyboard())
        return

    if quiet_if_recent:
        return

    await message.answer(
        "Контакт уже запрошен. Поделись номером через кнопку внизу чата, чтобы открыть доступ.",
        reply_markup=contact_keyboard(),
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    is_new_user = await storage.record_start(message.from_user, command.args)
    has_contact = await has_contact_access(storage, message.from_user.id)
    start_message = start_message_for_state(
        is_new_user=is_new_user,
        has_contact=has_contact,
    )
    if has_contact:
        await storage.mark_discord_access_sent(message.from_user)
        await message.answer(
            start_message,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            content.DISCORD_LINK_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
        return

    await message.answer(start_message, reply_markup=contact_keyboard())
    await storage.mark_contact_prompted(message.from_user)


@router.message(Command("help"))
async def handle_help(message: Message, storage: EventStorage) -> None:
    if message.from_user is not None:
        await storage.record_message_interaction(message.from_user, "help_requested")
    await message.answer(content.HELP_MESSAGE)


@router.message(Command("discord", "access"))
async def handle_discord_link(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    await storage.record_message_interaction(message.from_user, "discord_link_requested")
    if await has_contact_access(storage, message.from_user.id):
        await storage.mark_discord_access_sent(message.from_user)
        await message.answer(
            content.DISCORD_LINK_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
        return

    await send_contact_prompt(message, storage, force=False, quiet_if_recent=False)


@router.message(F.contact)
async def handle_contact(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None or message.contact is None:
        return

    if message.contact.user_id not in (None, message.from_user.id):
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


admin_commands(router)


@router.message()
async def handle_fallback(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None:
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
        return

    if is_command_text(message):
        await send_contact_prompt(message, storage, force=False, quiet_if_recent=False)
        return

    await send_contact_prompt(message, storage, force=False, quiet_if_recent=True)
