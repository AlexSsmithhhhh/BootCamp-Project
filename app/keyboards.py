from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import content


DISCORD_CTA_CALLBACK = "discord_cta"


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.START_CTA_BUTTON_TEXT,
                    callback_data=DISCORD_CTA_CALLBACK,
                )
            ]
        ]
    )


def discord_url_keyboard(discord_invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.DISCORD_URL_BUTTON_TEXT,
                    url=discord_invite_url,
                )
            ]
        ]
    )
