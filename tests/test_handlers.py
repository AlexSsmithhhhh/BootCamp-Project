import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import content
from app.handlers import (
    handle_discord_link,
    handle_fallback,
    handle_start,
    start_message_for_state,
)
from app.keyboards import (
    QUIZ_START_CALLBACK,
    WELCOME_SCHEDULE_CALLBACK,
    WELCOME_STREAMS_CALLBACK,
    quiz_start_keyboard,
    welcome_keyboard,
)
from app.quiz import EXECUTION_GAP, NO_GAP, ROUTINE_GAP, SYSTEM_GAP, score_quiz


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
