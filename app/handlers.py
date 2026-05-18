from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app import content
from app.config import Settings
from app.keyboards import DISCORD_CTA_CALLBACK, discord_url_keyboard, start_keyboard
from app.storage import EventStorage


router = Router()


@router.message(CommandStart())
async def handle_start(message: Message, storage: EventStorage) -> None:
    if message.from_user is not None:
        await storage.record_start(message.from_user)

    await message.answer(content.START_MESSAGE, reply_markup=start_keyboard())


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(content.HELP_MESSAGE)


@router.callback_query(F.data == DISCORD_CTA_CALLBACK)
async def handle_discord_cta(
    callback: CallbackQuery,
    storage: EventStorage,
    settings: Settings,
) -> None:
    await storage.ensure_user(callback.from_user)
    await storage.add_event(callback.from_user.id, "discord_cta_click")
    await callback.answer(content.DISCORD_CALLBACK_ACK)

    if callback.message is not None:
        await callback.message.answer(
            content.DISCORD_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
