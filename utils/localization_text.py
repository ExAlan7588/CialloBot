from __future__ import annotations

from typing import Any

TRANSLATION_MISSING_TEMPLATE = "<translation_missing: {key}>"
FORMAT_ERROR_TEMPLATE = "<formatting_error: {key} ({error_type})>"


def lookup_translation(
    translations: dict[str, dict[str, str]],
    *,
    lang_code: str,
    default_language: str,
    key: str,
    default_fallback: str,
) -> str:
    localized_string = translations.get(lang_code, {}).get(key)
    if localized_string is not None:
        return localized_string

    default_string = translations.get(default_language, {}).get(key)
    if default_string is not None:
        return default_string

    if default_fallback:
        return default_fallback

    return TRANSLATION_MISSING_TEMPLATE.format(key=key)


def format_translation(localized_string: str, key: str, *args: Any, **kwargs: Any) -> str:
    try:
        if args or kwargs:
            return localized_string.format(*args, **kwargs)
    except (IndexError, KeyError, TypeError) as exc:
        return FORMAT_ERROR_TEMPLATE.format(key=key, error_type=exc.__class__.__name__)
    else:
        return localized_string
