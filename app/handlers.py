from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message, ReplyKeyboardRemove

from app import content
from app.admin import admin_commands
from app.config import Settings
from app.keyboards import contact_keyboard, discord_url_keyboard
from app.storage import EventStorage


router = Router()
admin_commands(router)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject,
    storage: EventStorage,
) -> None:
    if message.from_user is not None:
        await storage.record_start(message.from_user, command.args)

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
async def handle_fallback(message: Message, storage: EventStorage) -> None:
    if message.from_user is not None:
        await storage.record_message_interaction(
            message.from_user,
            "fallback_message",
            {
                "content_type": str(message.content_type),
                "has_text": bool(message.text),
                "text_length": len(message.text or ""),
            },
        )
    await message.answer(content.CONTACT_REQUIRED_MESSAGE, reply_markup=contact_keyboard())
