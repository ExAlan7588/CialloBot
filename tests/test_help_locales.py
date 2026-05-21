from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
LOCALE_FILES = [ROOT / "locales" / "en.json", ROOT / "locales" / "zh_TW.json"]
REQUIRED_HELP_KEYS = ["cmd_desc_keyword_add", "cmd_desc_keyword_list"]


@pytest.mark.parametrize("locale_file", LOCALE_FILES, ids=lambda path: path.name)
def test_group_help_descriptions_exist_in_supported_locales(locale_file: Path) -> None:
    translations = json.loads(locale_file.read_text(encoding="utf-8"))

    for key in REQUIRED_HELP_KEYS:
        assert key in translations
        assert translations[key].strip()
