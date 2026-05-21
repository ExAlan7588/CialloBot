from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from private import config
from utils.localization_store import (
    load_json_object,
    serialize_preferences,
    validate_language_preferences,
    validate_translations,
)
from utils.localization_text import format_translation, lookup_translation

if TYPE_CHECKING:
    from collections.abc import Mapping

LOCALES_DIR = Path("locales")
USER_PREFS_FILE = Path("private/user_lang_prefs.json")

_translations: dict[str, dict[str, str]] = {}
_user_lang_preferences: dict[str, str] = {}
_prefs_lock = threading.Lock()


def _load_user_preferences() -> None:
    """Load user language preferences into memory."""
    if not USER_PREFS_FILE.exists():
        logger.info(f"'{USER_PREFS_FILE}' not found. Starting with empty user preferences.")
        _replace_user_preferences({})
        return

    content = USER_PREFS_FILE.read_text(encoding="utf-8")
    if not content:
        msg = f"{USER_PREFS_FILE} is empty; expected a JSON object"
        raise ValueError(msg)

    _replace_user_preferences(_load_preferences_from_json(content, USER_PREFS_FILE))
    logger.info(f"已成功從 '{USER_PREFS_FILE}' 加載用戶語言偏好。")


def _replace_user_preferences(preferences: Mapping[str, str]) -> None:
    with _prefs_lock:
        _user_lang_preferences.clear()
        _user_lang_preferences.update(dict(preferences))


def _load_preferences_from_json(content: str, path: Path) -> dict[str, str]:
    return _validate_language_preferences(path, load_json_object(content, path))


def _validate_language_preferences(path: Path, data: dict[Any, Any]) -> dict[str, str]:
    return validate_language_preferences(path, data, _supported_language_codes())


def _save_user_preferences() -> None:
    """Persist user language preferences to JSON."""
    with _prefs_lock:
        preferences_to_save = dict(_user_lang_preferences)
        USER_PREFS_FILE.write_text(serialize_preferences(preferences_to_save), encoding="utf-8")

    logger.debug(f"[L10N] Successfully saved to '{USER_PREFS_FILE}'.")


def load_language(lang_code: str) -> None:
    """Load a language file into the translation cache."""
    if lang_code not in _supported_language_codes():
        msg = f"Unsupported language code: {lang_code}"
        raise ValueError(msg)
    if lang_code in _translations:
        logger.debug(f"[L10N] Language {lang_code} already loaded. Skipping.")
        return

    file_path = LOCALES_DIR / f"{lang_code}.json"
    translations = load_json_object(file_path.read_text(encoding="utf-8"), file_path)
    _translations[lang_code] = _validate_translations(file_path, translations)
    logger.debug(f"[L10N] Successfully loaded language file: {file_path.name}")


def initialize_localization() -> None:
    """Load persisted language preferences and all configured locale files."""
    _load_user_preferences()
    load_language(config.DEFAULT_LANGUAGE)
    for lang_code in config.SUPPORTED_LANGUAGES:
        if lang_code not in _translations:
            load_language(str(lang_code))


def _validate_translations(path: Path, translations: dict[Any, Any]) -> dict[str, str]:
    return validate_translations(path, translations)


def get_user_language(user_id: int | str) -> str:
    """Return a user's language preference, or the configured default language."""
    lang_to_return = _user_lang_preferences.get(str(user_id), config.DEFAULT_LANGUAGE)
    logger.debug(f"[L10N] Returning lang: '{lang_to_return}' for user_id: '{user_id}'")
    return lang_to_return


def set_user_language(user_id: int | str, lang_code: str) -> bool:
    """Set a user's language preference."""
    if lang_code not in _supported_language_codes():
        logger.warning(f"嘗試設置不支持的語言 '{lang_code}' 給用戶 {user_id}")
        return False

    _user_lang_preferences[str(user_id)] = lang_code
    if lang_code not in _translations:
        load_language(lang_code)

    _save_user_preferences()
    logger.info(f"用戶 {user_id} 的語言已設置為: {lang_code}")
    return True


def get_localized_string(
    user_id_or_lang_code: int | str | None,
    key: str,
    default_fallback: str = "",
    *args: Any,
    **kwargs: Any,
) -> str:
    """Return a localized string using a user id, language code, or default language."""
    lang_code = _resolve_language_code(user_id_or_lang_code)
    localized_string = _lookup_translation(lang_code, key, default_fallback)
    return _format_translation(localized_string, key, *args, **kwargs)


def get_language_string(
    lang_code: str, key: str, default_fallback: str = "", *args: Any, **kwargs: Any
) -> str:
    """Return a localized string for an explicit language code."""
    localized_string = _lookup_translation(lang_code, key, default_fallback)
    return _format_translation(localized_string, key, *args, **kwargs)


def _resolve_language_code(user_id_or_lang_code: int | str | None) -> str:
    if user_id_or_lang_code is None:
        return config.DEFAULT_LANGUAGE

    direct_lang_code = str(user_id_or_lang_code)
    potential_lang = get_user_language(user_id_or_lang_code)
    if potential_lang in _translations:
        return potential_lang
    if direct_lang_code in _translations:
        return direct_lang_code
    return config.DEFAULT_LANGUAGE


def _supported_language_codes() -> set[str]:
    return {str(lang_code) for lang_code in config.SUPPORTED_LANGUAGES}


def _lookup_translation(lang_code: str, key: str, default_fallback: str) -> str:
    localized_string = lookup_translation(
        _translations,
        lang_code=lang_code,
        default_language=config.DEFAULT_LANGUAGE,
        key=key,
        default_fallback=default_fallback,
    )
    if localized_string.startswith("<translation_missing:"):
        logger.warning(
            f"[L10N] Key '{key}' not found in lang '{lang_code}' "
            f"or default '{config.DEFAULT_LANGUAGE}'."
        )
    return localized_string


def _format_translation(localized_string: str, key: str, *args: Any, **kwargs: Any) -> str:
    return format_translation(localized_string, key, *args, **kwargs)


lstr = get_localized_string
