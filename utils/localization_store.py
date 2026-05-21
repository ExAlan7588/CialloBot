from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def load_json_object(content: str, path: Path) -> dict[Any, Any]:
    data = json.loads(content)
    if not isinstance(data, dict):
        msg = f"{path} must contain a JSON object"
        raise TypeError(msg)
    return data


def validate_language_preferences(
    path: Path, data: dict[Any, Any], supported_language_codes: set[str]
) -> dict[str, str]:
    preferences: dict[str, str] = {}
    for user_id, lang_code in data.items():
        if not isinstance(user_id, str) or not user_id:
            msg = f"{path} contains an invalid user id key: {user_id!r}"
            raise TypeError(msg)
        if not isinstance(lang_code, str):
            msg = f"{path} contains a non-string language code for user {user_id!r}"
            raise TypeError(msg)
        if lang_code not in supported_language_codes:
            msg = f"{path} contains unsupported language code {lang_code!r} for user {user_id!r}"
            raise ValueError(msg)
        preferences[user_id] = lang_code
    return preferences


def validate_translations(path: Path, translations: dict[Any, Any]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in translations.items():
        if not isinstance(key, str) or not key:
            msg = f"{path} contains an invalid translation key: {key!r}"
            raise TypeError(msg)
        if not isinstance(value, str):
            msg = f"{path} contains a non-string translation for key {key!r}"
            raise TypeError(msg)
        validated[key] = value
    return validated


def serialize_preferences(preferences: dict[str, str]) -> str:
    return json.dumps(preferences, ensure_ascii=False, indent=4)
