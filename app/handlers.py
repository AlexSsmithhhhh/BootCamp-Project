import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app import content
from app.admin import admin_commands, is_admin
from app.config import Settings
from app.keyboards import (
    QUIZ_START_CALLBACK,
    WELCOME_SCHEDULE_CALLBACK,
    WELCOME_STREAMS_CALLBACK,
    contact_keyboard,
    quiz_start_keyboard,
    quiz_answer_keyboard,
    welcome_keyboard,
    discord_url_keyboard,
)
from app.quiz import (
    CATEGORY_LABELS,
    format_question,
    format_score_summary,
    get_option,
    get_question,
    question_count,
    result_for_key,
    score_quiz,
    tag_for_result,
)
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
    user=None,
    force: bool = False,
    quiet_if_recent: bool = False,
) -> None:
    prompt_user = user or message.from_user
    if prompt_user is None:
        return

    should_prompt = force or await storage.should_prompt_contact(
        prompt_user.id,
        cooldown_seconds=CONTACT_PROMPT_COOLDOWN_SECONDS,
    )
    if should_prompt:
        await storage.mark_contact_prompted(prompt_user)
        await message.answer(content.CONTACT_REQUIRED_MESSAGE, reply_markup=contact_keyboard())
        return

    if quiet_if_recent:
        return

    await message.answer(
        (
            "Контакт уже запрошен после результата диагностики. "
            "Поделись номером через кнопку внизу чата, чтобы открыть доступ."
        ),
        reply_markup=contact_keyboard(),
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject,
    storage: EventStorage,
) -> None:
    if message.from_user is None:
        return

    await storage.record_start(message.from_user, command.args)
    await message.answer(
        content.WELCOME_MESSAGE,
        reply_markup=quiz_start_keyboard(content.PASS_QUIZ_BUTTON_TEXT),
    )


@router.callback_query(F.data == WELCOME_STREAMS_CALLBACK)
async def handle_streams_info(
    callback: CallbackQuery,
    storage: EventStorage,
) -> None:
    await storage.record_message_interaction(callback.from_user, "welcome_streams_requested")
    if callback.message is None:
        await callback.answer("Не могу продолжить здесь.", show_alert=True)
        return

    await callback.message.answer(
        content.STREAMS_INFO_MESSAGE,
    )
    await callback.answer()


@router.callback_query(F.data == WELCOME_SCHEDULE_CALLBACK)
async def handle_schedule_info(
    callback: CallbackQuery,
    storage: EventStorage,
) -> None:
    await storage.record_message_interaction(callback.from_user, "welcome_schedule_requested")
    if callback.message is None:
        await callback.answer("Не могу продолжить здесь.", show_alert=True)
        return

    await callback.message.answer(
        content.SCHEDULE_INFO_MESSAGE,
    )
    await callback.answer()


@router.callback_query(F.data == QUIZ_START_CALLBACK)
async def handle_quiz_start(
    callback: CallbackQuery,
    storage: EventStorage,
) -> None:
    await storage.record_message_interaction(callback.from_user, "quiz_start_requested")
    if callback.message is None:
        await callback.answer("Не могу запустить тест здесь.", show_alert=True)
        return

    await storage.start_quiz_attempt(callback.from_user)
    await callback.message.answer(content.QUIZ_START_MESSAGE)
    await send_quiz_question(callback.message, 0)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^quiz:answer:\d+:[A-F]$"))
async def handle_quiz_answer(
    callback: CallbackQuery,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if callback.data is None:
        await callback.answer("Не могу прочитать ответ.", show_alert=True)
        return
    if callback.message is None:
        await callback.answer("Не могу продолжить здесь.", show_alert=True)
        return

    parsed_answer = parse_quiz_answer_callback(callback.data)
    if parsed_answer is None:
        await callback.answer("Не понял ответ.", show_alert=True)
        return

    question_index, answer_key = parsed_answer
    attempt = await storage.active_quiz_attempt(callback.from_user.id)
    if attempt is None:
        await callback.message.answer(
            content.DISCORD_REQUIRES_QUIZ_MESSAGE,
            reply_markup=quiz_start_keyboard(content.PASS_QUIZ_BUTTON_TEXT),
        )
        await callback.answer("Тест нужно начать заново.")
        return

    if int(attempt["current_question_index"]) != question_index:
        await callback.answer("Этот вопрос уже обработан.")
        current_question_index = int(attempt["current_question_index"])
        if current_question_index < question_count():
            await send_quiz_question(callback.message, current_question_index)
        return

    option = get_option(question_index, answer_key)
    updated_attempt = await storage.record_quiz_answer(
        user=callback.from_user,
        attempt_id=int(attempt["id"]),
        question_index=question_index,
        answer_key=option.key,
        category=option.category,
        category_label=CATEGORY_LABELS[option.category],
    )
    await callback.answer(f"Ответ {option.key} принят")

    next_question_index = int(updated_attempt["current_question_index"])
    if next_question_index < question_count():
        await send_quiz_question(callback.message, next_question_index)
        return

    outcome = score_quiz(updated_attempt["answers"])
    result_tag = tag_for_result(outcome.result_key)
    await storage.complete_quiz_attempt(
        user=callback.from_user,
        attempt_id=int(updated_attempt["id"]),
        result_key=outcome.result_key,
        result_tag=result_tag,
        scores=outcome.scores,
    )
    await callback.message.answer(format_quiz_result_message(outcome.result_key, outcome.scores))
    await send_post_quiz_info(callback.message)

    if await has_contact_access(storage, callback.from_user.id):
        await storage.mark_discord_access_sent(callback.from_user)
        await callback.message.answer(
            content.DISCORD_LINK_MESSAGE,
            reply_markup=discord_url_keyboard(settings.discord_invite_url),
        )
        return

    await send_contact_prompt(callback.message, storage, user=callback.from_user, force=True)


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
    completed_attempt = await storage.latest_completed_quiz_attempt(message.from_user.id)
    if completed_attempt is not None:
        if await has_contact_access(storage, message.from_user.id):
            await storage.mark_discord_access_sent(message.from_user)
            await message.answer(
                content.DISCORD_LINK_MESSAGE,
                reply_markup=discord_url_keyboard(settings.discord_invite_url),
            )
            return

        await send_contact_prompt(message, storage, force=True)
        return

    await message.answer(
        content.DISCORD_REQUIRES_QUIZ_MESSAGE,
        reply_markup=quiz_start_keyboard(content.PASS_QUIZ_BUTTON_TEXT),
    )


@router.message(F.contact)
async def handle_contact(
    message: Message,
    storage: EventStorage,
    settings: Settings,
) -> None:
    if message.from_user is None or message.contact is None:
        return

    completed_attempt = await storage.latest_completed_quiz_attempt(message.from_user.id)
    if completed_attempt is None:
        await storage.record_message_interaction(
            message.from_user,
            "contact_rejected_before_quiz_result",
        )
        await message.answer(
            content.DISCORD_REQUIRES_QUIZ_MESSAGE,
            reply_markup=quiz_start_keyboard(content.PASS_QUIZ_BUTTON_TEXT),
        )
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

    completed_attempt = await storage.latest_completed_quiz_attempt(message.from_user.id)
    if completed_attempt is not None:
        if has_contact:
            await storage.mark_discord_access_sent(message.from_user)
            await message.answer(
                content.DISCORD_LINK_MESSAGE,
                reply_markup=discord_url_keyboard(settings.discord_invite_url),
            )
            return

        await send_contact_prompt(message, storage, force=True)
        return

    await message.answer(
        content.DISCORD_REQUIRES_QUIZ_MESSAGE,
        reply_markup=quiz_start_keyboard(content.PASS_QUIZ_BUTTON_TEXT),
    )


async def send_quiz_question(message: Message, question_index: int) -> None:
    question = get_question(question_index)
    await message.answer(
        format_question(question_index),
        reply_markup=quiz_answer_keyboard(question_index, question),
    )


async def send_post_quiz_info(message: Message) -> None:
    await message.answer(
        content.POST_QUIZ_INFO_MESSAGE,
        reply_markup=welcome_keyboard(),
    )


def parse_quiz_answer_callback(data: str) -> tuple[int, str] | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "quiz" or parts[1] != "answer":
        return None
    try:
        question_index = int(parts[2])
    except ValueError:
        return None
    answer_key = parts[3].upper()
    if answer_key not in {"A", "B", "C", "D", "E", "F"}:
        return None
    return question_index, answer_key


def format_quiz_result_message(result_key: str, scores: dict[str, int]) -> str:
    result = result_for_key(result_key)
    return (
        f"{result.message}\n\n"
        "<b>Распределение баллов:</b>\n"
        f"{format_score_summary(scores)}\n\n"
        "Чтобы получить доступ к серверу, осталось оставить контакт."
    )
