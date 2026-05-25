from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app import content
from app.quiz import QuizQuestion, answer_display_label


WELCOME_STREAMS_CALLBACK = "welcome:streams"
WELCOME_SCHEDULE_CALLBACK = "welcome:schedule"
QUIZ_START_CALLBACK = "quiz:start"
QUIZ_ANSWER_PREFIX = "quiz:answer"
QUIZ_BACK_PREFIX = "quiz:back"
DISCORD_OPEN_CALLBACK = "discord:open"


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=content.SHARE_CONTACT_BUTTON_TEXT,
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.WELCOME_STREAMS_BUTTON_TEXT,
                    callback_data=WELCOME_STREAMS_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text=content.WELCOME_SCHEDULE_BUTTON_TEXT,
                    callback_data=WELCOME_SCHEDULE_CALLBACK,
                )
            ],
        ]
    )


def quiz_start_keyboard(
    button_text: str = content.START_QUIZ_BUTTON_TEXT,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=QUIZ_START_CALLBACK,
                )
            ]
        ]
    )


def quiz_answer_callback(question_index: int, answer_key: str) -> str:
    return f"{QUIZ_ANSWER_PREFIX}:{question_index}:{answer_key}"


def quiz_back_callback(question_index: int) -> str:
    return f"{QUIZ_BACK_PREFIX}:{question_index}"


def quiz_answer_keyboard(
    question_index: int,
    question: QuizQuestion,
) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=answer_display_label(option.key),
                callback_data=quiz_answer_callback(question_index, option.key),
            )
            for option in question.options[index : index + 3]
        ]
        for index in range(0, len(question.options), 3)
    ]
    if question_index > 0:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=quiz_back_callback(question_index),
                )
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=keyboard,
    )


def discord_url_keyboard(discord_invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.DISCORD_URL_BUTTON_TEXT,
                    url=discord_invite_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text=content.WELCOME_STREAMS_BUTTON_TEXT,
                    callback_data=WELCOME_STREAMS_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text=content.WELCOME_SCHEDULE_BUTTON_TEXT,
                    callback_data=WELCOME_SCHEDULE_CALLBACK,
                )
            ],
        ]
    )


def discord_generated_link_keyboard(discord_invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.DISCORD_URL_BUTTON_TEXT,
                    url=discord_invite_url,
                )
            ],
        ]
    )


def discord_open_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=content.DISCORD_GENERATE_BUTTON_TEXT,
                    callback_data=DISCORD_OPEN_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text=content.WELCOME_STREAMS_BUTTON_TEXT,
                    callback_data=WELCOME_STREAMS_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text=content.WELCOME_SCHEDULE_BUTTON_TEXT,
                    callback_data=WELCOME_SCHEDULE_CALLBACK,
                )
            ],
        ]
    )
