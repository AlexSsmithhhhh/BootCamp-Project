import unittest

from app import content
from app.handlers import start_message_for_state


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


if __name__ == "__main__":
    unittest.main()
