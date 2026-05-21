from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import discord
from loguru import logger

from utils.beatmap_utils import get_beatmap_status_display
from utils.localization import get_localized_string as lstr
from utils.localization import get_user_language

from .osu_constants import (
    MODE_EMOJI_STRINGS,
    RANK_COLORS,
    RANK_EMOJI_MAP,
    RANK_HD_FL_SS_EMOJI,
    RANK_SH_EMOJI,
    RANK_XH_EMOJI,
)
from .osu_formatting import format_mods_for_display

if TYPE_CHECKING:
    from collections.abc import Callable

    from utils.osu_api import OsuAPI


class ModeNameResolver(Protocol):
    def __call__(self, mode_int: int, user_id_for_l10n: int, *, name_only: bool = False) -> str:
        """Return a localized osu! mode name."""
        ...


@dataclass(frozen=True, kw_only=True)
class ScoreEmbedRequest:
    score_data: dict[str, Any]
    player_name: str
    player_avatar_url: str | None
    mode_int: int
    user_id_for_l10n: int
    rank_in_top: int | None = None


@dataclass(frozen=True, kw_only=True)
class ScoreValue:
    value: int
    v1_fallback_failed: bool


@dataclass(frozen=True, kw_only=True)
class ScoreEmbedBuilder:
    osu_api: OsuAPI
    mode_name_resolver: ModeNameResolver
    na_value_resolver: Callable[[int], str]

    async def create(self, request: ScoreEmbedRequest) -> discord.Embed:
        logger.debug(
            f"[_create_score_embed] Called for player: {request.player_name}, "
            f"mode_int: {request.mode_int}, rank_in_top: {request.rank_in_top}"
        )
        embed = _create_base_embed(request)
        score_value = await self._add_score_fields(embed, request)
        _add_status_and_mode_fields(embed, request, self.mode_name_resolver)
        _add_hits_field(embed, request)
        _set_cover_image(embed, request.score_data)
        _set_footer(embed, request, score_value)
        return embed

    async def _add_score_fields(
        self, embed: discord.Embed, request: ScoreEmbedRequest
    ) -> ScoreValue:
        score_value = await self._resolve_score_value(request)
        mods = _format_mods(request.score_data, request.user_id_for_l10n)
        rank_emoji = _resolve_rank_emoji(request.score_data, mods)
        pp_value = request.score_data.get("pp")

        embed.add_field(
            name=lstr(request.user_id_for_l10n, "score_label", "Score"),
            value=f"{score_value.value:,}",
            inline=True,
        )
        embed.add_field(
            name=lstr(request.user_id_for_l10n, "accuracy_label", "Accuracy"),
            value=f"{request.score_data.get('accuracy', 0.0) * 100:.2f}%",
            inline=True,
        )
        embed.add_field(
            name=lstr(request.user_id_for_l10n, "rank_label", "Rank"), value=rank_emoji, inline=True
        )
        embed.add_field(
            name=lstr(request.user_id_for_l10n, "combo_label", "Combo"),
            value=f"{request.score_data.get('max_combo', 0)}x",
            inline=True,
        )
        embed.add_field(
            name=lstr(request.user_id_for_l10n, "mods_label", "Mods"),
            value=mods or self.na_value_resolver(request.user_id_for_l10n),
            inline=True,
        )
        embed.add_field(
            name=lstr(request.user_id_for_l10n, "pp_label", "PP"),
            value=_format_pp(pp_value, self.na_value_resolver(request.user_id_for_l10n)),
            inline=True,
        )
        return score_value

    async def _resolve_score_value(self, request: ScoreEmbedRequest) -> ScoreValue:
        score_value = int(request.score_data.get("score", 0) or 0)
        pp_value = request.score_data.get("pp")
        if score_value != 0 or pp_value is None or pp_value <= 0:
            return ScoreValue(value=score_value, v1_fallback_failed=False)

        logger.info(
            f"[_create_score_embed] API v2 score is 0 for a play with {pp_value} PP "
            f"(Mode: {request.mode_int}). Attempting API v1 fallback."
        )
        return await self._fetch_v1_score(request, score_value)

    async def _fetch_v1_score(self, request: ScoreEmbedRequest, current_score: int) -> ScoreValue:
        beatmap_id = request.score_data.get("beatmap", {}).get("id")
        user_id = request.score_data.get("user_id")
        if not beatmap_id or not user_id:
            return ScoreValue(value=current_score, v1_fallback_failed=True)

        try:
            v1_score_data = await self.osu_api.get_score_v1(
                beatmap_id=beatmap_id, user_id=user_id, mode=request.mode_int
            )
        except Exception:
            logger.exception("[_create_score_embed] Error during API v1 fallback")
            return ScoreValue(value=current_score, v1_fallback_failed=True)

        return _resolve_v1_score_value(
            v1_score_data, current_score, beatmap_id, user_id, request.mode_int
        )


def _create_base_embed(request: ScoreEmbedRequest) -> discord.Embed:
    score_data = request.score_data
    beatmap_data = score_data.get("beatmap", {})
    beatmap_url = beatmap_data.get("url", f"https://osu.ppy.sh/b/{beatmap_data.get('id')}")
    title = _format_embed_title(request)
    beatmap_title = _format_beatmap_title(score_data, request.user_id_for_l10n)
    embed_color = RANK_COLORS.get(str(score_data.get("rank", "F")).upper(), discord.Color.default())

    embed = discord.Embed(
        title=title, description=f"**[{beatmap_title}]({beatmap_url})**", color=embed_color
    )
    _set_author(embed, request)
    return embed


def _format_embed_title(request: ScoreEmbedRequest) -> str:
    if request.rank_in_top is None:
        fallback = f"Recent play for {request.player_name}"
        return lstr(request.user_id_for_l10n, "recent_embed_title", fallback, request.player_name)

    fallback = f"{request.player_name}'s Best #{request.rank_in_top}"
    return lstr(
        request.user_id_for_l10n,
        "best_embed_title",
        fallback,
        request.player_name,
        request.rank_in_top,
    )


def _format_beatmap_title(score_data: dict[str, Any], user_id_for_l10n: int) -> str:
    beatmap_data = score_data.get("beatmap", {})
    beatmapset_data = score_data.get("beatmapset", {})
    na_value = lstr(user_id_for_l10n, "value_not_available", "N/A")
    artist = beatmapset_data.get("artist", na_value)
    title = beatmapset_data.get("title", na_value)
    version = beatmap_data.get("version", na_value)
    mods = format_mods_for_display(score_data.get("mods", []))
    return f"{artist} - {title} [{version}] {mods}".strip()


def _set_author(embed: discord.Embed, request: ScoreEmbedRequest) -> None:
    author_url = f"https://osu.ppy.sh/users/{request.score_data['user_id']}"
    if request.player_avatar_url:
        embed.set_author(
            name=request.player_name, icon_url=request.player_avatar_url, url=author_url
        )
        return

    embed.set_author(name=request.player_name, url=author_url)


def _resolve_v1_score_value(
    v1_score_data: dict[str, Any] | None,
    current_score: int,
    beatmap_id: int,
    user_id: int | str,
    mode_int: int,
) -> ScoreValue:
    if not v1_score_data:
        _log_missing_v1_score(beatmap_id, user_id, mode_int)
        return ScoreValue(value=current_score, v1_fallback_failed=True)

    raw_score = v1_score_data.get("score")
    if raw_score is None:
        _log_missing_v1_score(beatmap_id, user_id, mode_int)
        return ScoreValue(value=current_score, v1_fallback_failed=True)

    return _parse_v1_score_value(raw_score, current_score, beatmap_id, user_id, mode_int)


def _parse_v1_score_value(
    raw_score: Any, current_score: int, beatmap_id: int, user_id: int | str, mode_int: int
) -> ScoreValue:
    try:
        score_value = int(raw_score)
    except (TypeError, ValueError):
        logger.warning(
            f"[_create_score_embed] Could not parse score '{raw_score}' from API v1 as int."
        )
        return ScoreValue(value=current_score, v1_fallback_failed=True)

    logger.info(
        f"[_create_score_embed] Successfully updated score to {score_value} using API v1 fallback "
        f"for beatmap {beatmap_id}, user {user_id}, mode {mode_int}."
    )
    return ScoreValue(value=score_value, v1_fallback_failed=False)


def _log_missing_v1_score(beatmap_id: int, user_id: int | str, mode_int: int) -> None:
    logger.info(
        f"[_create_score_embed] API v1 fallback did not return valid score data for "
        f"beatmap {beatmap_id}, user {user_id}, mode {mode_int}."
    )


def _format_mods(score_data: dict[str, Any], user_id_for_l10n: int) -> str:
    mods = score_data.get("mods", [])
    return "".join(mods) if mods else lstr(user_id_for_l10n, "mods_nomod", "No Mod")


def _resolve_rank_emoji(score_data: dict[str, Any], mods: str) -> str:
    rank_key = str(score_data.get("rank", "F")).upper()
    rank_emoji = _base_rank_emoji(rank_key)
    if rank_key == "X" and _has_hd_or_fl(mods):
        return RANK_HD_FL_SS_EMOJI
    if rank_key == "S" and _has_hd_or_fl(mods):
        return RANK_SH_EMOJI
    return rank_emoji


def _base_rank_emoji(rank_key: str) -> str:
    if rank_key == "XH":
        return RANK_XH_EMOJI
    if rank_key == "SH":
        return RANK_SH_EMOJI
    return RANK_EMOJI_MAP.get(rank_key, rank_key)


def _has_hd_or_fl(mods: str) -> bool:
    return "HD" in mods or "FL" in mods


def _format_pp(pp_value: Any, na_value: str) -> str:
    return f"{pp_value:.2f}pp" if pp_value is not None else na_value


def _add_status_and_mode_fields(
    embed: discord.Embed, request: ScoreEmbedRequest, mode_name_resolver: ModeNameResolver
) -> None:
    beatmapset_data = request.score_data.get("beatmapset", {})
    raw_status = _resolve_raw_status(beatmapset_data)
    status_display = get_beatmap_status_display(raw_status, request.user_id_for_l10n, lstr)
    mode_name = mode_name_resolver(request.mode_int, request.user_id_for_l10n, name_only=True)

    embed.add_field(
        name=lstr(request.user_id_for_l10n, "pp_embed_beatmap_status", "Beatmap Status"),
        value=status_display,
        inline=True,
    )
    embed.add_field(
        name=lstr(request.user_id_for_l10n, "user_profile_game_mode", "Game Mode"),
        value=f"{MODE_EMOJI_STRINGS.get(request.mode_int, '')} {mode_name}",
        inline=True,
    )


def _resolve_raw_status(beatmapset_data: dict[str, Any]) -> str | int | None:
    raw_status = beatmapset_data.get("status")
    return raw_status if isinstance(raw_status, str) else beatmapset_data.get("ranked")


def _add_hits_field(embed: discord.Embed, request: ScoreEmbedRequest) -> None:
    hits = _format_hits(request.score_data.get("statistics", {}), request.mode_int)
    if not hits:
        return

    embed.add_field(
        name=lstr(request.user_id_for_l10n, "hits_label", "Hits"), value=hits, inline=True
    )


def _format_hits(stats: dict[str, Any], mode_int: int) -> str:
    if mode_int in {0, 2}:
        return _join_hit_counts(stats, ("count_300", "count_100", "count_50", "count_miss"))
    if mode_int == 1:
        return _join_hit_counts(stats, ("count_300", "count_100", "count_miss"))
    if mode_int == 3:
        return _join_hit_counts(
            stats, ("count_geki", "count_300", "count_katu", "count_100", "count_50", "count_miss")
        )
    return ""


def _join_hit_counts(stats: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "/".join(str(stats.get(key, 0)) for key in keys)


def _set_cover_image(embed: discord.Embed, score_data: dict[str, Any]) -> None:
    cover_url = score_data.get("beatmapset", {}).get("covers", {}).get("cover")
    if cover_url:
        embed.set_image(url=cover_url)


def _set_footer(embed: discord.Embed, request: ScoreEmbedRequest, score_value: ScoreValue) -> None:
    footer_parts = [_format_footer_date(request)]
    footer_parts.append(_format_lazer_note(request, score_value))
    visible_parts = [part for part in footer_parts if part]
    if visible_parts:
        embed.set_footer(text=" | ".join(visible_parts))


def _format_footer_date(request: ScoreEmbedRequest) -> str | None:
    created_at = request.score_data.get("created_at")
    if not created_at:
        return None

    played_at = datetime.datetime.fromisoformat(created_at)
    lang_code = get_user_language(str(request.user_id_for_l10n))
    return played_at.strftime("%Y/%m/%d %H:%M" if lang_code == "zh_TW" else "%Y-%m-%d %H:%M")


def _format_lazer_note(request: ScoreEmbedRequest, score_value: ScoreValue) -> str | None:
    if not score_value.v1_fallback_failed:
        return None

    pp_value = request.score_data.get("pp")
    if score_value.value != 0 or pp_value is None or pp_value <= 0:
        return None

    return lstr(
        request.user_id_for_l10n,
        "score_footer_note_lazer",
        "※ This score may be unavailable due to Lazer or legacy plays",
    )
