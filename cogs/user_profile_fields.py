from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from .osu_constants import MODE_EMOJI_STRINGS
from .user_formatting import get_country_flag_emoji

if TYPE_CHECKING:
    import discord

    from .user_formatting import UserFormatter
    from .user_profile import ProfileRenderContext


GRADE_SSH_EMOJI = "<:rkhdfl:1373246417350561844>"
GRADE_SS_EMOJI = "<:rkss:1373246926379679836>"
GRADE_SH_EMOJI = "<:rkshdfl:1373964175671427143>"
GRADE_S_EMOJI = "<:rks:1373246734079230072>"
GRADE_A_EMOJI = "<:rka:1373246979211132988>"


@dataclass(frozen=True, kw_only=True)
class ProfileStatusValues:
    rank: str
    country_rank: str
    level: str
    pp: str
    accuracy: str
    grades: str
    playcount: str
    total_score: str
    average_score: str
    ranked_score: str
    average_ranked_score: str
    total_hits: str
    average_hits: str
    max_combo: str
    replays: str


def add_standard_profile_fields(embed: discord.Embed, context: ProfileRenderContext) -> None:
    player_data = context.player_data
    if player_data.get("cover_url"):
        embed.set_image(url=player_data["cover_url"])

    _add_primary_stat_fields(embed, context)
    _add_profile_meta_fields(embed, context)


def profile_status_values(context: ProfileRenderContext) -> ProfileStatusValues:
    stats = context.mode_stats
    na = context.formatter.na(context.user_id_for_l10n)
    playcount = _playcount_value(context.player_data, stats)
    total_score = _stat_value(stats, "total_score")
    ranked_score = _stat_value(stats, "ranked_score")
    total_hits = _stat_value(stats, "total_hits")
    return ProfileStatusValues(
        rank=_rank_text(stats, "global_rank", na),
        country_rank=_country_rank_text(context.player_data, stats, na),
        level=_level_detail(stats, na),
        pp=_pp_detail_text(stats, na),
        accuracy=_accuracy_detail_text(stats, na),
        grades=_grades_text(context.player_data),
        playcount=integer_text(playcount, na),
        total_score=integer_text(total_score, na),
        average_score=_average_text(total_score, playcount, na),
        ranked_score=integer_text(ranked_score, na),
        average_ranked_score=_average_text(ranked_score, playcount, na),
        total_hits=integer_text(total_hits, na),
        average_hits=_average_text(total_hits, playcount, na),
        max_combo=integer_text(_stat_value(stats, "maximum_combo"), na),
        replays=integer_text(_stat_value(stats, "replays_watched_by_others"), na),
    )


def integer_text(value: Any, na: str) -> str:
    if value is None:
        return na
    return f"`{value:,}`"


def previous_names(
    player_data: dict[str, Any], formatter: UserFormatter, user_id_for_l10n: int
) -> str:
    previous_usernames = player_data.get("previous_usernames")
    if not previous_usernames:
        return formatter.na(user_id_for_l10n)
    return ", ".join(previous_usernames)


def playstyle_text(player_data: dict[str, Any], na: str) -> str:
    playstyle = player_data.get("playstyle")
    if not playstyle:
        return na
    return ", ".join(playstyle)


def achievement_text(player_data: dict[str, Any], na: str) -> str:
    achievements = player_data.get("user_achievements")
    logger.debug(f"[USER_COG profile] Raw achievements data: {achievements}")
    if achievements is None:
        return na
    return f"`{len(achievements)}`"


def playtime_text(stats: dict[str, Any] | None, na: str) -> str:
    total_seconds = _stat_value(stats, "play_time")
    if not total_seconds:
        return na
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"`{hours}h {minutes}m`"


def join_date_text(join_date_value: Any, formatter: UserFormatter, user_id_for_l10n: int) -> str:
    if not join_date_value:
        return formatter.na(user_id_for_l10n)
    try:
        join_dt = datetime.datetime.fromisoformat(join_date_value)
    except ValueError:
        logger.warning(f"Could not parse join_date for detail view: {join_date_value}")
        return str(join_date_value)
    formatted_date = formatter.datetime_text(join_dt, user_id_for_l10n)
    relative_time = formatter.time_since(join_dt, user_id_for_l10n)
    if relative_time == formatter.na(user_id_for_l10n):
        return formatted_date
    return f"{formatted_date} ({relative_time})"


def profile_link_lines(player_data: dict[str, Any]) -> list[str]:
    link_lines: list[str] = []
    if twitter_username := player_data.get("twitter"):
        link_lines.append(f"Twitter: [{twitter_username}](https://x.com/{twitter_username})")
    if discord_contact := player_data.get("discord"):
        link_lines.append(f"Discord: {discord_contact}")
    return link_lines


def _add_primary_stat_fields(embed: discord.Embed, context: ProfileRenderContext) -> None:
    stats = context.mode_stats
    formatter = context.formatter
    user_id = context.user_id_for_l10n
    na = formatter.na(user_id)
    field_specs = (
        ("user_profile_pp", _pp_text(stats, na)),
        ("user_profile_accuracy", _accuracy_text(stats, na)),
        ("user_profile_level", _level_summary(stats, na)),
        ("user_profile_global_rank", _rank_text(stats, "global_rank", na)),
        ("user_profile_country_rank", _country_rank_text(context.player_data, stats, na)),
        ("user_profile_play_count", _playcount_text(context.player_data, stats, na)),
    )
    for key, value in field_specs:
        embed.add_field(name=formatter.lstr_or_na(user_id, key), value=value, inline=True)


def _add_profile_meta_fields(embed: discord.Embed, context: ProfileRenderContext) -> None:
    formatter = context.formatter
    user_id = context.user_id_for_l10n
    embed.add_field(
        name=formatter.lstr_or_na(user_id, "user_profile_join_date"),
        value=_join_date_summary(context.player_data.get("join_date"), formatter, user_id),
        inline=False,
    )
    embed.add_field(
        name=formatter.lstr_or_na(user_id, "user_profile_game_mode"),
        value=_mode_summary(context),
        inline=False,
    )


def _stat_value(stats: dict[str, Any] | None, key: str) -> Any:
    if not stats:
        return None
    return stats.get(key)


def _playcount_value(player_data: dict[str, Any], stats: dict[str, Any] | None) -> Any:
    if stats and stats.get("play_count") is not None:
        return stats.get("play_count")
    return player_data.get("play_count")


def _rank_text(stats: dict[str, Any] | None, key: str, na: str) -> str:
    rank = _stat_value(stats, key)
    if rank is None:
        return na
    return f"`#{rank:,}`"


def _country_rank_text(player_data: dict[str, Any], stats: dict[str, Any] | None, na: str) -> str:
    country_rank = _stat_value(stats, "country_rank")
    if country_rank is None:
        return na
    country_flag = get_country_flag_emoji(player_data.get("country_code", ""))
    return f"{country_flag} `#{country_rank:,}`"


def _pp_text(stats: dict[str, Any] | None, na: str) -> str:
    pp_value = _stat_value(stats, "pp")
    if pp_value is None:
        return na
    return f"{pp_value:,.2f}pp"


def _pp_detail_text(stats: dict[str, Any] | None, na: str) -> str:
    pp_value = _stat_value(stats, "pp")
    if pp_value is None:
        return na
    return f"`{pp_value:,.2f}`"


def _accuracy_text(stats: dict[str, Any] | None, na: str) -> str:
    accuracy = _stat_value(stats, "hit_accuracy")
    if accuracy is None:
        return na
    return f"{accuracy:,.2f}%"


def _accuracy_detail_text(stats: dict[str, Any] | None, na: str) -> str:
    accuracy = _stat_value(stats, "hit_accuracy")
    if accuracy is None:
        return na
    return f"`{accuracy:,.2f}%`"


def _level_summary(stats: dict[str, Any] | None, na: str) -> str:
    level = stats.get("level", {}) if stats else {}
    level_current = level.get("current")
    if level_current is None:
        return na
    return f"{level_current}.{int(level.get('progress', 0.0)):02d}"


def _level_detail(stats: dict[str, Any] | None, na: str) -> str:
    level = stats.get("level", {}) if stats else {}
    level_current = level.get("current")
    if level_current is None:
        return na
    return f"`{level_current} + {level.get('progress', 0):.2f}%`"


def _playcount_text(player_data: dict[str, Any], stats: dict[str, Any] | None, na: str) -> str:
    playcount = _playcount_value(player_data, stats)
    if playcount is None:
        return na
    return f"{playcount:,}"


def _average_text(total: Any, playcount: Any, na: str) -> str:
    if not total or not playcount or playcount <= 0:
        return na
    return f"`{total / playcount:,.2f}`"


def _grades_text(player_data: dict[str, Any]) -> str:
    grade_counts = player_data.get("statistics", {}).get("grade_counts", {})
    return (
        f"{GRADE_SSH_EMOJI} `{grade_counts.get('ssh', 0)}` "
        f"{GRADE_SS_EMOJI} `{grade_counts.get('ss', 0)}` "
        f"{GRADE_SH_EMOJI} `{grade_counts.get('sh', 0)}` "
        f"{GRADE_S_EMOJI} `{grade_counts.get('s', 0)}` "
        f"{GRADE_A_EMOJI} `{grade_counts.get('a', 0)}`"
    )


def _join_date_summary(
    join_date_value: Any, formatter: UserFormatter, user_id_for_l10n: int
) -> str:
    if not join_date_value:
        return formatter.na(user_id_for_l10n)
    try:
        join_dt = datetime.datetime.fromisoformat(join_date_value)
    except ValueError:
        logger.warning(f"Could not parse join_date_str: {join_date_value}")
        return str(join_date_value)
    return f"{formatter.datetime_text(join_dt, user_id_for_l10n)} ({formatter.time_since(join_dt, user_id_for_l10n)})"


def _mode_summary(context: ProfileRenderContext) -> str:
    mode_emoji = MODE_EMOJI_STRINGS.get(context.current_mode_int, "")
    mode_name = context.formatter.mode_name(context.current_mode_int, context.user_id_for_l10n)
    return f"{mode_emoji} {mode_name}".strip()
