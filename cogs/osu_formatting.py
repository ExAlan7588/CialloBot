from __future__ import annotations

from collections.abc import Callable

from loguru import logger

from utils.localization import get_language_string, get_user_language

from .osu_constants import MODE_FALLBACK_TEXT, OSU_MODES_L10N_KEYS, OSU_MODES_NAME_ONLY_L10N_KEYS

LocalizedStringGetter = Callable[[int | str, str, str], str]


def format_mods_for_display(mod_list: list[str]) -> str:
    if not mod_list:
        return ""
    return "+" + "".join(mod_list).upper()


def format_score_mods(mod_list: list[str], user_id_for_l10n: int | str) -> str:
    if not mod_list:
        return get_language_string(get_user_language(str(user_id_for_l10n)), "mods_nomod", "No Mod")
    return "".join(mod_list)


def get_osu_mode_name(
    mode_int: int,
    user_id_for_l10n: int | str,
    *,
    name_only: bool = False,
    fallback_getter: LocalizedStringGetter | None = None,
    log_prefix: str = "OSU_MODE",
) -> str:
    logger.debug(
        f"[{log_prefix} get_osu_mode_name] Called with mode_int: {mode_int}, "
        f"user_id: {user_id_for_l10n}, name_only: {name_only}"
    )
    key_map = OSU_MODES_NAME_ONLY_L10N_KEYS if name_only else OSU_MODES_L10N_KEYS
    fallback_key = "mode_name_only_unknown" if name_only else "mode_unknown"
    l10n_key = key_map.get(mode_int, fallback_key)
    fallback = MODE_FALLBACK_TEXT.get(mode_int, "Unknown Mode")

    if fallback_getter is not None:
        localized_name = fallback_getter(user_id_for_l10n, l10n_key, fallback)
    else:
        current_lang = get_user_language(str(user_id_for_l10n))
        localized_name = get_language_string(current_lang, l10n_key, fallback)

    logger.debug(f"[{log_prefix} get_osu_mode_name] Result: {localized_name}")
    return localized_name
