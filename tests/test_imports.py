import unittest


class ImportTests(unittest.TestCase):
    def test_app_main_imports(self) -> None:
        import app.main  # noqa: F401


if __name__ == "__main__":
    unittest.main()
