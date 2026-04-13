from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCALE_FILES = [
    ROOT / "locales" / "en.json",
    ROOT / "locales" / "zh_TW.json",
]
REQUIRED_BREAD_KEYS = [
    "cmd_desc_bread_profile",
    "cmd_desc_bread_buy",
    "cmd_desc_bread_eat",
    "cmd_desc_bread_give",
    "cmd_desc_bread_rob",
    "cmd_desc_bread_bet",
    "cmd_desc_bread_rank",
    "cmd_desc_bread_record",
    "cmd_desc_bread_nickname",
    "cmd_desc_bread_itemname",
]


class HelpLocaleTests(unittest.TestCase):
    def test_bread_help_descriptions_exist_in_supported_locales(self) -> None:
        for locale_file in LOCALE_FILES:
            with self.subTest(locale=locale_file.name):
                translations = json.loads(locale_file.read_text(encoding="utf-8"))
                for key in REQUIRED_BREAD_KEYS:
                    self.assertIn(key, translations)
                    self.assertTrue(translations[key].strip())


if __name__ == "__main__":
    unittest.main()
