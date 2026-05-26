from pathlib import Path


ASSETS_DIR = Path(__file__).resolve().parent / "assets"

WELCOME_IMAGE_PATH = ASSETS_DIR / "welcome.png"
SCHEDULE_IMAGE_PATH = ASSETS_DIR / "schedule.png"
DISCORD_ACCESS_IMAGE_PATH = ASSETS_DIR / "discord-access.png"

QUIZ_RESULT_IMAGE_PATHS = {
    "system": ASSETS_DIR / "result-system.png",
    "routine": ASSETS_DIR / "result-routine.png",
    "journal": ASSETS_DIR / "result-journal.png",
    "execution": ASSETS_DIR / "result-execution.png",
    "psychology": ASSETS_DIR / "result-psychology.png",
    "no_gap": ASSETS_DIR / "result-no-gap.png",
}


def result_image_path(result_key: str) -> Path:
    return QUIZ_RESULT_IMAGE_PATHS[result_key]
