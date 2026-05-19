import unittest

from app.admin import parse_media_caption_command


class AdminCommandTests(unittest.TestCase):
    def test_parses_direct_media_post_caption(self) -> None:
        self.assertEqual(
            parse_media_caption_command("/post Photo caption"),
            ("post", "Photo caption"),
        )

    def test_parses_direct_media_broadcast_caption_with_bot_name(self) -> None:
        self.assertEqual(
            parse_media_caption_command("/broadcast@BootcampBot Broadcast caption"),
            ("broadcast", "Broadcast caption"),
        )

    def test_ignores_regular_caption(self) -> None:
        self.assertIsNone(parse_media_caption_command("Regular photo caption"))


if __name__ == "__main__":
    unittest.main()
