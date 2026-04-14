from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCALE_FILES = [
    ROOT / "locales" / "en.json",
    ROOT / "locales" / "zh_TW.json",
]
REQUIRED_HELP_KEYS = [
    "cmd_desc_keyword_add",
    "cmd_desc_keyword_list",
]


class HelpLocaleTests(unittest.TestCase):
    def test_group_help_descriptions_exist_in_supported_locales(self) -> None:
        for locale_file in LOCALE_FILES:
            with self.subTest(locale=locale_file.name):
                translations = json.loads(locale_file.read_text(encoding="utf-8"))
                for key in REQUIRED_HELP_KEYS:
                    self.assertIn(key, translations)
                    self.assertTrue(translations[key].strip())


if __name__ == "__main__":
    unittest.main()
