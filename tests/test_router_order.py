import unittest

from app.handlers import router


class RouterOrderTests(unittest.TestCase):
    def test_public_commands_are_registered_before_admin_catch_all(self) -> None:
        callback_names = [handler.callback.__name__ for handler in router.message.handlers]

        self.assertLess(
            callback_names.index("handle_start"),
            callback_names.index("handle_admin_post_draft_message"),
        )
        self.assertLess(
            callback_names.index("handle_discord_link"),
            callback_names.index("handle_admin_post_draft_message"),
        )
        self.assertLess(
            callback_names.index("handle_contact"),
            callback_names.index("handle_admin_post_draft_message"),
        )
        self.assertLess(
            callback_names.index("handle_admin_post_draft_message"),
            callback_names.index("handle_fallback"),
        )


if __name__ == "__main__":
    unittest.main()
