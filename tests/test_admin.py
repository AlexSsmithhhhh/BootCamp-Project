import unittest
from datetime import timezone

from app.admin import (
    normalize_plain_command,
    parse_media_caption_command,
    parse_post_schedule_input,
)


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

    def test_normalizes_plain_commands(self) -> None:
        self.assertEqual(normalize_plain_command("/new_post"), "new post")
        self.assertEqual(normalize_plain_command("all post"), "all post")
        self.assertEqual(normalize_plain_command("/delete 7"), "delete 7")

    def test_parses_post_schedule_input_as_utc(self) -> None:
        parsed = parse_post_schedule_input("2026-05-20 14:00")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
