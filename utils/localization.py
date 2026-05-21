from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from private import config

LOCALES_DIR = Path("locales")
USER_PREFS_FILE = Path("private/user_lang_prefs.json")
TRANSLATION_MISSING_TEMPLATE = "<translation_missing: {key}>"
FORMAT_ERROR_TEMPLATE = "<formatting_error: {key} ({error_type})>"

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
        logger.info(f"'{USER_PREFS_FILE}' is empty. Starting with empty user preferences.")
        _replace_user_preferences({})
        return

    data = json.loads(content)
    if not isinstance(data, dict):
        msg = f"{USER_PREFS_FILE} must contain a JSON object"
        raise TypeError(msg)

    _replace_user_preferences({str(user_id): str(lang_code) for user_id, lang_code in data.items()})
    logger.info(f"已成功從 '{USER_PREFS_FILE}' 加載用戶語言偏好。")


def _replace_user_preferences(preferences: dict[str, str]) -> None:
    with _prefs_lock:
        _user_lang_preferences.clear()
        _user_lang_preferences.update(preferences)


def _save_user_preferences() -> None:
    """Persist user language preferences to JSON."""
    with _prefs_lock:
        preferences_to_save = dict(_user_lang_preferences)
        USER_PREFS_FILE.write_text(
            json.dumps(preferences_to_save, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    logger.debug(f"[L10N] Successfully saved to '{USER_PREFS_FILE}'.")


def load_language(lang_code: str) -> None:
    """Load a language file into the translation cache."""
    if lang_code in _translations:
        logger.debug(f"[L10N] Language {lang_code} already loaded. Skipping.")
        return

    file_path = LOCALES_DIR / f"{lang_code}.json"
    translations = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(translations, dict):
        msg = f"{file_path} must contain a JSON object"
        raise TypeError(msg)

    _translations[lang_code] = {str(key): str(value) for key, value in translations.items()}
    logger.debug(f"[L10N] Successfully loaded language file: {file_path.name}")


def get_user_language(user_id: int | str) -> str:
    """Return a user's language preference, or the configured default language."""
    lang_to_return = _user_lang_preferences.get(str(user_id), config.DEFAULT_LANGUAGE)
    logger.debug(f"[L10N] Returning lang: '{lang_to_return}' for user_id: '{user_id}'")
    return lang_to_return


def set_user_language(user_id: int | str, lang_code: str) -> bool:
    """Set a user's language preference."""
    if lang_code not in config.SUPPORTED_LANGUAGES:
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


def _lookup_translation(lang_code: str, key: str, default_fallback: str) -> str:
    localized_string = _translations.get(lang_code, {}).get(key)
    if localized_string is not None:
        return localized_string

    default_string = _translations.get(config.DEFAULT_LANGUAGE, {}).get(key)
    if default_string is not None:
        return default_string

    if default_fallback:
        return default_fallback

    logger.warning(
        f"[L10N] Key '{key}' not found in lang '{lang_code}' "
        f"or default '{config.DEFAULT_LANGUAGE}'."
    )
    return TRANSLATION_MISSING_TEMPLATE.format(key=key)


def _format_translation(localized_string: str, key: str, *args: Any, **kwargs: Any) -> str:
    try:
        if args or kwargs:
            return localized_string.format(*args, **kwargs)
    except (IndexError, KeyError, TypeError) as exc:
        return FORMAT_ERROR_TEMPLATE.format(key=key, error_type=exc.__class__.__name__)
    else:
        return localized_string


_load_user_preferences()
load_language(config.DEFAULT_LANGUAGE)

for lang in config.SUPPORTED_LANGUAGES:
    if lang not in _translations:
        load_language(lang)

lstr = get_localized_string
