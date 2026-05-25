import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import ReplyKeyboardRemove

from app import content
from app.discord_invites import DiscordInvite
from app.handlers import (
    format_quiz_result_message,
    handle_contact,
    handle_discord_open,
    handle_discord_link,
    handle_fallback,
    handle_manual_phone_entry,
    handle_quiz_answer,
    handle_quiz_start,
    handle_start,
    normalize_phone_number,
    send_quiz_result_message,
    start_message_for_state,
)
from app.keyboards import (
    DISCORD_OPEN_CALLBACK,
    QUIZ_START_CALLBACK,
    WELCOME_SCHEDULE_CALLBACK,
    WELCOME_STREAMS_CALLBACK,
    quiz_answer_keyboard,
    quiz_start_keyboard,
    welcome_keyboard,
)
from app.quiz import (
    EXECUTION_GAP,
    NO_GAP,
    ROUTINE_GAP,
    SYSTEM_GAP,
    format_question,
    get_question,
    score_quiz,
)


class StartFlowTests(unittest.TestCase):
    def test_first_start_gets_welcome_contact_prompt(self) -> None:
        self.assertEqual(
            start_message_for_state(is_new_user=True, has_contact=False),
            content.START_MESSAGE,
        )

    def test_repeat_start_without_contact_gets_returning_prompt(self) -> None:
        self.assertEqual(
            start_message_for_state(is_new_user=False, has_contact=False),
            content.RETURNING_WITHOUT_CONTACT_MESSAGE,
        )

    def test_repeat_start_with_contact_skips_contact_prompt(self) -> None:
        self.assertEqual(
            start_message_for_state(is_new_user=False, has_contact=True),
            content.RETURNING_WITH_CONTACT_MESSAGE,
        )


class StartHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_sends_bootcamp_welcome_with_info_buttons(self) -> None:
        user = SimpleNamespace(id=1001)
        command = SimpleNamespace(args="utm_source_instagram")
        message = SimpleNamespace(from_user=user, answer=AsyncMock())
        storage = SimpleNamespace(record_start=AsyncMock())

        await handle_start(message, command, storage)

        storage.record_start.assert_awaited_once_with(user, "utm_source_instagram")
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        sent_keyboard = message.answer.await_args.kwargs["reply_markup"]

        self.assertEqual(sent_text, content.WELCOME_MESSAGE)
        self.assertEqual(
            sent_keyboard.inline_keyboard[0][0].callback_data,
            QUIZ_START_CALLBACK,
        )

    async def test_quiz_start_keeps_welcome_static_and_sends_first_question(self) -> None:
        user = SimpleNamespace(id=1001)
        message = SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock())
        callback = SimpleNamespace(from_user=user, message=message, answer=AsyncMock())
        storage = SimpleNamespace(
            record_message_interaction=AsyncMock(),
            start_quiz_attempt=AsyncMock(),
        )

        await handle_quiz_start(callback, storage)

        storage.record_message_interaction.assert_awaited_once_with(
            user,
            "quiz_start_requested",
        )
        storage.start_quiz_attempt.assert_awaited_once_with(user)
        message.edit_text.assert_not_called()
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        sent_keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertIn("Вопрос 1 из 7", sent_text)
        self.assertEqual(sent_keyboard.inline_keyboard[0][0].callback_data, "quiz:answer:0:A")
        callback.answer.assert_awaited_once_with("Начинаем диагностику")


class DiscordAccessGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_command_routes_user_to_quiz_first(self) -> None:
        user = SimpleNamespace(id=1001)
        message = SimpleNamespace(from_user=user, answer=AsyncMock())
        storage = SimpleNamespace(
            record_message_interaction=AsyncMock(),
            latest_completed_quiz_attempt=AsyncMock(return_value=None),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_discord_link(message, storage, settings)

        storage.record_message_interaction.assert_awaited_once_with(
            user,
            "discord_link_requested",
        )
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        sent_keyboard = message.answer.await_args.kwargs["reply_markup"]

        self.assertEqual(sent_text, content.DISCORD_REQUIRES_QUIZ_MESSAGE)
        self.assertEqual(
            sent_keyboard.inline_keyboard[0][0].callback_data,
            QUIZ_START_CALLBACK,
        )


class FallbackGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_routes_user_to_quiz_without_contact_prompt(self) -> None:
        user = SimpleNamespace(id=1002, username=None)
        message = SimpleNamespace(
            from_user=user,
            content_type="text",
            text="hello",
            answer=AsyncMock(),
        )
        storage = SimpleNamespace(
            record_message_interaction=AsyncMock(),
            user_has_contact=AsyncMock(return_value=False),
            latest_completed_quiz_attempt=AsyncMock(return_value=None),
        )
        settings = SimpleNamespace(
            telegram_admin_ids=frozenset(),
            telegram_admin_usernames=frozenset(),
        )

        await handle_fallback(message, storage, settings)

        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        sent_keyboard = message.answer.await_args.kwargs["reply_markup"]

        self.assertEqual(sent_text, content.DISCORD_REQUIRES_QUIZ_MESSAGE)
        self.assertEqual(
            sent_keyboard.inline_keyboard[0][0].callback_data,
            QUIZ_START_CALLBACK,
        )


class ContactFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_contact_unlocks_discord_button_only(self) -> None:
        user = SimpleNamespace(id=3003)
        contact = SimpleNamespace(user_id=3003)
        message = SimpleNamespace(from_user=user, contact=contact, answer=AsyncMock())
        storage = SimpleNamespace(
            latest_completed_quiz_attempt=AsyncMock(return_value={"id": 1}),
            save_contact=AsyncMock(),
            mark_discord_access_sent=AsyncMock(),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_contact(message, storage, settings)

        storage.save_contact.assert_awaited_once_with(user, contact)
        storage.mark_discord_access_sent.assert_awaited_once_with(user)
        self.assertEqual(message.answer.await_count, 2)

        cleanup_message = message.answer.await_args_list[0]
        discord_message = message.answer.await_args_list[1]

        self.assertEqual(cleanup_message.args[0], content.CONTACT_KEYBOARD_REMOVAL_MESSAGE)
        self.assertIsInstance(cleanup_message.kwargs["reply_markup"], ReplyKeyboardRemove)
        message.answer.return_value.delete.assert_awaited_once()
        self.assertEqual(discord_message.args[0], content.DISCORD_LINK_MESSAGE)
        self.assertIn("Отлично, контакт получен", discord_message.args[0])
        self.assertIn("#start-here", discord_message.args[0])
        self.assertEqual(len(discord_message.kwargs["reply_markup"].inline_keyboard), 3)
        self.assertEqual(
            discord_message.kwargs["reply_markup"].inline_keyboard[0][0].text,
            content.DISCORD_GENERATE_BUTTON_TEXT,
        )
        self.assertEqual(
            discord_message.kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
            DISCORD_OPEN_CALLBACK,
        )
        self.assertEqual(
            discord_message.kwargs["reply_markup"].inline_keyboard[1][0].callback_data,
            WELCOME_STREAMS_CALLBACK,
        )
        self.assertEqual(
            discord_message.kwargs["reply_markup"].inline_keyboard[2][0].callback_data,
            WELCOME_SCHEDULE_CALLBACK,
        )

    async def test_discord_open_callback_records_click_and_reveals_url(self) -> None:
        user = SimpleNamespace(id=3004)
        message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
        callback = SimpleNamespace(from_user=user, message=message, answer=AsyncMock())
        storage = SimpleNamespace(
            latest_completed_quiz_attempt=AsyncMock(return_value={"id": 1}),
            user_has_contact=AsyncMock(return_value=True),
            mark_discord_open_clicked=AsyncMock(),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_discord_open(callback, storage, settings)

        storage.mark_discord_open_clicked.assert_awaited_once_with(user)
        message.edit_reply_markup.assert_not_called()
        message.answer.assert_awaited_once()
        generated_message = message.answer.await_args
        generated_keyboard = generated_message.kwargs["reply_markup"]

        self.assertEqual(generated_message.args[0], content.DISCORD_LINK_READY_MESSAGE)
        self.assertEqual(len(generated_keyboard.inline_keyboard), 1)
        self.assertEqual(
            generated_keyboard.inline_keyboard[0][0].text,
            content.DISCORD_URL_BUTTON_TEXT,
        )
        self.assertEqual(
            generated_keyboard.inline_keyboard[0][0].url,
            "https://discord.gg/test",
        )
        callback.answer.assert_awaited_once_with("Ссылка сгенерирована")


    async def test_discord_open_generates_unique_single_use_invite(self) -> None:
        user = SimpleNamespace(id=3006)
        message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
        callback = SimpleNamespace(from_user=user, message=message, answer=AsyncMock())
        storage = SimpleNamespace(
            latest_completed_quiz_attempt=AsyncMock(return_value={"id": 1}),
            user_has_contact=AsyncMock(return_value=True),
            mark_discord_open_clicked=AsyncMock(),
            latest_active_discord_invite=AsyncMock(return_value=None),
            save_discord_invite=AsyncMock(),
            mark_discord_invite_generation_failed=AsyncMock(),
        )
        settings = SimpleNamespace(
            discord_invite_url="https://discord.gg/fallback",
            discord_bot_token="discord-token",
            discord_invite_channel_id="123456789",
            discord_invite_max_age_seconds=3600,
        )

        with patch(
            "app.handlers.create_discord_invite",
            AsyncMock(return_value=DiscordInvite(code="unique-code", url="https://discord.gg/unique-code")),
        ) as create_invite:
            await handle_discord_open(callback, storage, settings)

        create_invite.assert_awaited_once()
        storage.save_discord_invite.assert_awaited_once()
        saved_kwargs = storage.save_discord_invite.await_args.kwargs
        self.assertEqual(saved_kwargs["invite_code"], "unique-code")
        self.assertEqual(saved_kwargs["invite_url"], "https://discord.gg/unique-code")
        self.assertEqual(saved_kwargs["channel_id"], "123456789")
        self.assertEqual(saved_kwargs["max_uses"], 1)
        self.assertEqual(saved_kwargs["max_age_seconds"], 3600)

        message.edit_reply_markup.assert_not_called()
        message.answer.assert_awaited_once()
        generated_keyboard = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(
            generated_keyboard.inline_keyboard[0][0].url,
            "https://discord.gg/unique-code",
        )


class ManualPhoneEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_phone_entry_unlocks_discord_for_admin_user(self) -> None:
        user = SimpleNamespace(id=3007, first_name="Admin", last_name=None)
        message = SimpleNamespace(
            from_user=user,
            text="+380 98 707 93 01",
            answer=AsyncMock(),
        )
        storage = SimpleNamespace(
            save_contact=AsyncMock(),
            mark_discord_access_sent=AsyncMock(),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_manual_phone_entry(message, storage, settings)

        storage.save_contact.assert_awaited_once()
        saved_contact = storage.save_contact.await_args.args[1]
        self.assertEqual(saved_contact.phone_number, "+380987079301")
        storage.mark_discord_access_sent.assert_awaited_once_with(user)
        self.assertEqual(message.answer.await_count, 2)
        self.assertEqual(
            message.answer.await_args_list[0].args[0],
            content.CONTACT_KEYBOARD_REMOVAL_MESSAGE,
        )
        message.answer.return_value.delete.assert_awaited_once()
        self.assertEqual(message.answer.await_args_list[1].args[0], content.DISCORD_LINK_MESSAGE)

    async def test_manual_phone_entry_reprompts_on_partial_plus(self) -> None:
        user = SimpleNamespace(id=3008, first_name="Admin", last_name=None)
        message = SimpleNamespace(from_user=user, text="+", answer=AsyncMock())
        storage = SimpleNamespace(
            save_contact=AsyncMock(),
            mark_discord_access_sent=AsyncMock(),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_manual_phone_entry(message, storage, settings)

        storage.save_contact.assert_not_called()
        message.answer.assert_awaited_once()
        self.assertEqual(message.answer.await_args.args[0], content.MANUAL_PHONE_INVALID_MESSAGE)
        self.assertEqual(
            message.answer.await_args.kwargs["reply_markup"].keyboard[0][0].text,
            content.SHARE_CONTACT_BUTTON_TEXT,
        )


class PhoneNumberParsingTests(unittest.TestCase):
    def test_normalizes_phone_variants(self) -> None:
        self.assertEqual(normalize_phone_number("+380 98 707 93 01"), "+380987079301")
        self.assertEqual(normalize_phone_number("380987079301"), "+380987079301")
        self.assertEqual(normalize_phone_number("098 707 93 01"), "+380987079301")
        self.assertIsNone(normalize_phone_number("+"))
        self.assertIsNone(normalize_phone_number("new post"))


class QuizResultMessageTests(unittest.TestCase):
    def test_quiz_result_message_hides_score_summary_and_contact_hint(self) -> None:
        text = format_quiz_result_message(
            SYSTEM_GAP,
            {
                SYSTEM_GAP: 2,
                ROUTINE_GAP: 1,
                NO_GAP: 0,
            },
        )

        self.assertIn("Твоя проблема", text)
        self.assertIn("Твой результат", text)
        self.assertIn("BootCamp Open Week", text)
        self.assertNotIn("Распределение баллов", text)
        self.assertNotIn("System Gap", text)
        self.assertNotIn("оставить контакт", text)


class QuizResultFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_quiz_result_is_new_message_after_inline_test(self) -> None:
        message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())

        await send_quiz_result_message(message, SYSTEM_GAP, {SYSTEM_GAP: 1})

        message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        message.answer.assert_awaited_once()
        sent_text = message.answer.await_args.args[0]
        self.assertIn("Твоя проблема", sent_text)
        self.assertIn("Твой результат", sent_text)

    async def test_completed_quiz_always_requests_contact_for_full_flow(self) -> None:
        user = SimpleNamespace(id=3005)
        message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
        callback = SimpleNamespace(
            from_user=user,
            message=message,
            data="quiz:answer:6:A",
            answer=AsyncMock(),
        )
        storage = SimpleNamespace(
            active_quiz_attempt=AsyncMock(
                return_value={
                    "id": 44,
                    "current_question_index": 6,
                },
            ),
            record_quiz_answer=AsyncMock(
                return_value={
                    "id": 44,
                    "current_question_index": 7,
                    "answers": [
                        {
                            "question_index": 6,
                            "answer_key": "A",
                            "category": SYSTEM_GAP,
                        }
                    ],
                },
            ),
            complete_quiz_attempt=AsyncMock(),
            mark_contact_prompted=AsyncMock(),
        )
        settings = SimpleNamespace(discord_invite_url="https://discord.gg/test")

        await handle_quiz_answer(callback, storage, settings)

        storage.complete_quiz_attempt.assert_awaited_once()
        storage.mark_contact_prompted.assert_awaited_once_with(user)
        self.assertEqual(message.answer.await_count, 2)
        self.assertEqual(message.answer.await_args_list[1].args[0], content.CONTACT_REQUIRED_MESSAGE)


class PostQuizInfoKeyboardTests(unittest.TestCase):
    def test_welcome_keyboard_has_two_post_quiz_info_branches(self) -> None:
        keyboard = welcome_keyboard()

        self.assertEqual(len(keyboard.inline_keyboard), 2)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            WELCOME_STREAMS_CALLBACK,
        )
        self.assertEqual(
            keyboard.inline_keyboard[1][0].callback_data,
            WELCOME_SCHEDULE_CALLBACK,
        )

    def test_quiz_start_keyboard_points_to_single_quiz_callback(self) -> None:
        keyboard = quiz_start_keyboard("Start")

        self.assertEqual(len(keyboard.inline_keyboard), 1)
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "Start")
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            QUIZ_START_CALLBACK,
        )

    def test_quiz_answer_keyboard_adds_back_button_after_first_question(self) -> None:
        first_keyboard = quiz_answer_keyboard(0, get_question(0))
        second_keyboard = quiz_answer_keyboard(1, get_question(1))

        self.assertNotEqual(first_keyboard.inline_keyboard[-1][0].text, "⬅️ Назад")
        self.assertEqual(second_keyboard.inline_keyboard[-1][0].text, "⬅️ Назад")
        self.assertEqual(second_keyboard.inline_keyboard[-1][0].callback_data, "quiz:back:1")

    def test_quiz_shows_numeric_answer_labels(self) -> None:
        question_text = format_question(0)
        keyboard = quiz_answer_keyboard(0, get_question(0))
        button_texts = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("<b>1.</b>", question_text)
        self.assertIn("<b>6.</b>", question_text)
        self.assertIn("<b>Вопрос 1 из 7</b>", question_text)
        self.assertIn("<b>Варианты ответа:</b>", question_text)
        self.assertIn("Нажми номер ответа ниже.", question_text)
        self.assertNotIn("<b>A.</b>", question_text)
        self.assertEqual(button_texts, ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "quiz:answer:0:A")


class QuizScoringTests(unittest.TestCase):
    def test_highest_gap_wins(self) -> None:
        outcome = score_quiz(
            [
                {"question_index": 0, "category": SYSTEM_GAP},
                {"question_index": 1, "category": SYSTEM_GAP},
                {"question_index": 2, "category": ROUTINE_GAP},
            ]
        )

        self.assertEqual(outcome.result_key, SYSTEM_GAP)
        self.assertEqual(outcome.scores[SYSTEM_GAP], 2)

    def test_seventh_question_breaks_problem_tie(self) -> None:
        outcome = score_quiz(
            [
                {"question_index": 0, "category": SYSTEM_GAP},
                {"question_index": 1, "category": EXECUTION_GAP},
                {"question_index": 6, "category": EXECUTION_GAP},
                {"question_index": 2, "category": SYSTEM_GAP},
            ]
        )

        self.assertEqual(outcome.result_key, EXECUTION_GAP)

    def test_no_gap_loses_tie_to_actionable_problem(self) -> None:
        outcome = score_quiz(
            [
                {"question_index": 0, "category": NO_GAP},
                {"question_index": 1, "category": SYSTEM_GAP},
            ]
        )

        self.assertEqual(outcome.result_key, SYSTEM_GAP)


if __name__ == "__main__":
    unittest.main()
