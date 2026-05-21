from __future__ import annotations

import datetime
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta
from loguru import logger

from utils.localization import get_localized_string as lstr

from .osu_formatting import get_osu_mode_name

DEFAULT_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
GLOBE_EMOJI = "🌍"
REGIONAL_INDICATOR_OFFSET = 127397


def get_country_flag_emoji(country_code: str | None) -> str:
    if not country_code or len(country_code) != 2:
        return GLOBE_EMOJI

    normalized_code = country_code.upper()
    return chr(REGIONAL_INDICATOR_OFFSET + ord(normalized_code[0])) + chr(
        REGIONAL_INDICATOR_OFFSET + ord(normalized_code[1])
    )


@dataclass(frozen=True)
class UserFormatter:
    def na(self, user_id_for_l10n: int | str) -> str:
        potential_na = lstr(user_id_for_l10n, "value_not_available", "N/A")
        if "__LSTR_KEY_ERRORuser_profile_title__" in potential_na:
            logger.warning(
                "[USER_COG] lstr returned unexpected placeholder for 'value_not_available'."
            )
            return "無法取得"
        if _is_l10n_error(potential_na) or potential_na == "value_not_available":
            logger.warning(
                "[USER_COG] lstr failed for 'value_not_available'. "
                f"Using hardcoded fallback. Original: {potential_na}"
            )
            return "N/A"
        return potential_na

    def lstr_or_na(self, user_id_for_l10n: int | str, key: str, *args: object) -> str:
        missing_placeholder = f"__LSTR_KEY_ERROR__{key}__"
        raw_translation = lstr(user_id_for_l10n, key, missing_placeholder, *args)
        if raw_translation == missing_placeholder or _is_l10n_error(raw_translation):
            return self.na(user_id_for_l10n)
        return raw_translation

    def mode_name(self, mode_int: int, user_id_for_l10n: int | str) -> str:
        return get_osu_mode_name(
            mode_int,
            user_id_for_l10n,
            fallback_getter=lstr,
            log_prefix="USER_COG",
        )

    def datetime_text(
        self,
        dt_obj: datetime.datetime | None,
        user_id_for_l10n: int | str,
        *,
        format_key: str = "date_format",
    ) -> str:
        if dt_obj is None:
            return self.na(user_id_for_l10n)

        format_str = lstr(user_id_for_l10n, format_key, "")
        if not format_str or _is_l10n_error(format_str) or format_str == format_key:
            format_str = DEFAULT_DATETIME_FORMAT
        return dt_obj.strftime(format_str.strip())

    def time_since(
        self, dt_obj: datetime.datetime | None, user_id_for_l10n: int | str, *, short: bool = True
    ) -> str:
        if dt_obj is None:
            return lstr(user_id_for_l10n, "never_uploaded", "Never")

        diff = relativedelta(datetime.datetime.now(datetime.UTC), _aware_datetime(dt_obj))
        parts = _relative_parts(diff, user_id_for_l10n)
        if parts:
            return _join_relative_parts(parts, user_id_for_l10n, short)
        if not short:
            return f"0{lstr(user_id_for_l10n, 'unit_day', 'd')}"
        return f"{max(diff.seconds, 0)}{lstr(user_id_for_l10n, 'unit_second', 's')}"


def _is_l10n_error(value: str) -> bool:
    return "<translation_missing" in value or "<formatting_error" in value


def _aware_datetime(dt_obj: datetime.datetime) -> datetime.datetime:
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=datetime.UTC)
    return dt_obj


def _relative_parts(diff: relativedelta, user_id_for_l10n: int | str) -> list[str]:
    component_specs = (
        (diff.years, "unit_year", "y"),
        (diff.months, "unit_month", "m"),
        (diff.days, "unit_day", "d"),
    )
    return [
        f"{value}{lstr(user_id_for_l10n, unit_key, default_unit)}"
        for value, unit_key, default_unit in component_specs
        if value > 0
    ]


def _join_relative_parts(parts: list[str], user_id_for_l10n: int | str, short: bool) -> str:
    if short:
        return parts[0]
    parts_to_join = parts[:2]
    lang_code = lstr(user_id_for_l10n, "_lang_code", "en")
    if lang_code.startswith("zh"):
        return "".join(parts_to_join)
    return " ".join(parts_to_join)
