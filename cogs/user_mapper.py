from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from utils import user_data_manager
from utils.localization import get_localized_string as lstr

from .user_errors import UserCommandError

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI

    from .user_formatting import UserFormatter


MAPPER_BEATMAP_TYPES = ("ranked", "loved", "graveyard", "pending", "nominated")
MAPPER_PAGE_LIMIT = 50
MAPPER_MAX_FETCHES_PER_TYPE = 1000
RANKED_LOVED_STATUSES = {"ranked", "loved", "qualified", "approved"}
ZERO_WIDTH_SPACE = "\u200b"


@dataclass(frozen=True, kw_only=True)
class MapperCommandInput:
    osu_user: str | None
    osu_id: int | None


@dataclass(frozen=True, kw_only=True)
class MapperLookup:
    user_identifier: str
    identifier_type: str | None


@dataclass(frozen=True, kw_only=True)
class MappingStats:
    total_mapsets: int
    ranked_loved_sets: int
    total_favourites: int
    kudosu_total: Any
    followers_count: Any
    guest_diffs_count: Any
    earliest_submission_date: datetime.datetime | None
    latest_submission_date: datetime.datetime | None
    latest_beatmapset: dict[str, Any] | None


@dataclass(frozen=True, kw_only=True)
class MapperRenderContext:
    player_data: dict[str, Any]
    stats: MappingStats
    user_id_for_l10n: int
    formatter: UserFormatter


class UserMapperService:
    def __init__(self, osu_api: OsuAPI, formatter: UserFormatter) -> None:
        self.osu_api = osu_api
        self.formatter = formatter

    async def send_mapper(
        self, interaction: discord.Interaction, command_input: MapperCommandInput
    ) -> None:
        user_id_for_l10n = interaction.user.id
        lookup = await _resolve_mapper_lookup(user_id_for_l10n, command_input)
        player_data = await self._fetch_player(lookup)
        if not player_data:
            raise UserCommandError(
                self.formatter.lstr_or_na(
                    user_id_for_l10n, "error_user_not_found", lookup.user_identifier
                )
            )

        actual_user_id = _require_player_id(player_data)
        username = player_data.get("username", lookup.user_identifier)
        logger.debug(f"[USER_COG /mapper] Fetched user: ID {actual_user_id}, Username: {username}")

        beatmapsets = await self._fetch_all_beatmapsets(actual_user_id)
        stats = _mapping_stats(player_data, beatmapsets)
        embed = _build_mapper_embed(
            MapperRenderContext(
                player_data=player_data,
                stats=stats,
                user_id_for_l10n=user_id_for_l10n,
                formatter=self.formatter,
            )
        )
        logger.debug(f"[USER_COG /mapper] Sending embed for {username}")
        await interaction.followup.send(embed=embed)

    async def _fetch_player(self, lookup: MapperLookup) -> dict[str, Any]:
        if lookup.identifier_type == "username":
            return await self.osu_api.get_user(
                user_identifier=lookup.user_identifier, identifier_type=lookup.identifier_type
            )
        return await self.osu_api.get_user(user_identifier=lookup.user_identifier)

    async def _fetch_all_beatmapsets(self, user_id: int | str) -> list[dict[str, Any]]:
        all_beatmapsets: dict[Any, dict[str, Any]] = {}
        for beatmap_type in MAPPER_BEATMAP_TYPES:
            await self._fetch_beatmapsets_by_type(
                user_id, beatmap_type, all_beatmapsets=all_beatmapsets
            )

        logger.debug(f"[USER_COG /mapper] Total unique beatmapsets fetched: {len(all_beatmapsets)}")
        return list(all_beatmapsets.values())

    async def _fetch_beatmapsets_by_type(
        self, user_id: int | str, beatmap_type: str, *, all_beatmapsets: dict[Any, dict[str, Any]]
    ) -> None:
        offset = 0
        fetched_count = 0
        while fetched_count < MAPPER_MAX_FETCHES_PER_TYPE:
            page = await self.osu_api.get_user_beatmapsets(
                user_id=user_id, beatmap_type=beatmap_type, limit=MAPPER_PAGE_LIMIT, offset=offset
            )
            if not page:
                return

            _merge_beatmapset_page(all_beatmapsets, page, beatmap_type)
            fetched_count += len(page)
            if len(page) < MAPPER_PAGE_LIMIT:
                return
            offset += len(page)

        logger.warning(
            f"[USER_COG /mapper] Reached fetch cap {MAPPER_MAX_FETCHES_PER_TYPE} for {beatmap_type}."
        )


async def _resolve_mapper_lookup(
    user_id_for_l10n: int, command_input: MapperCommandInput
) -> MapperLookup:
    if command_input.osu_user and command_input.osu_id is not None:
        raise UserCommandError(lstr(user_id_for_l10n, "error_only_one_identifier"), ephemeral=True)
    if command_input.osu_id is not None:
        return MapperLookup(user_identifier=str(command_input.osu_id), identifier_type=None)
    if command_input.osu_user:
        user_identifier = command_input.osu_user.strip()
        identifier_type = "username" if user_identifier.isdigit() else None
        return MapperLookup(user_identifier=user_identifier, identifier_type=identifier_type)

    bound_user = await user_data_manager.get_user_binding(user_id_for_l10n)
    if bound_user:
        return MapperLookup(user_identifier=str(bound_user), identifier_type=None)
    raise UserCommandError(lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound"))


def _require_player_id(player_data: dict[str, Any]) -> int | str:
    user_id = player_data.get("id")
    if user_id is None:
        msg = "mapper player payload missing id"
        raise TypeError(msg)
    return user_id


def _merge_beatmapset_page(
    all_beatmapsets: dict[Any, dict[str, Any]], page: list[Any], beatmap_type: str
) -> None:
    for beatmapset in page:
        if not isinstance(beatmapset, dict):
            msg = f"mapper {beatmap_type} beatmapset item must be an object"
            raise TypeError(msg)
        beatmapset_id = beatmapset.get("id")
        if beatmapset_id is None:
            msg = f"mapper {beatmap_type} beatmapset item missing id"
            raise TypeError(msg)
        all_beatmapsets[beatmapset_id] = beatmapset


def _mapping_stats(player_data: dict[str, Any], beatmapsets: list[dict[str, Any]]) -> MappingStats:
    latest_submission_date: datetime.datetime | None = None
    earliest_submission_date: datetime.datetime | None = None
    latest_beatmapset: dict[str, Any] | None = None
    ranked_loved_sets = 0
    total_favourites = 0
    for beatmapset in beatmapsets:
        ranked_loved_sets += int(beatmapset.get("status") in RANKED_LOVED_STATUSES)
        total_favourites += int(beatmapset.get("favourite_count", 0) or 0)
        parsed_date = _parse_submission_date(beatmapset)
        if parsed_date is None:
            continue
        if latest_submission_date is None or parsed_date > latest_submission_date:
            latest_submission_date = parsed_date
            latest_beatmapset = beatmapset
        if earliest_submission_date is None or parsed_date < earliest_submission_date:
            earliest_submission_date = parsed_date

    return MappingStats(
        total_mapsets=len(beatmapsets),
        ranked_loved_sets=ranked_loved_sets,
        total_favourites=total_favourites,
        kudosu_total=player_data.get("kudosu", {}).get("total"),
        followers_count=player_data.get("follower_count"),
        guest_diffs_count=player_data.get("guest_beatmapset_count"),
        earliest_submission_date=earliest_submission_date,
        latest_submission_date=latest_submission_date,
        latest_beatmapset=latest_beatmapset,
    )


def _parse_submission_date(beatmapset: dict[str, Any]) -> datetime.datetime | None:
    raw_date = beatmapset.get("submitted_date") or beatmapset.get("last_updated")
    if not raw_date:
        return None
    try:
        return datetime.datetime.fromisoformat(raw_date)
    except ValueError:
        logger.warning(f"[USER_COG /mapper] Could not parse date: {raw_date}")
        return None


def _build_mapper_embed(context: MapperRenderContext) -> discord.Embed:
    embed = discord.Embed(color=discord.Color.purple())
    _set_mapper_author(embed, context.player_data, context.user_id_for_l10n)
    _add_mapper_stats_fields(embed, context)
    _add_latest_submission_field(embed, context)
    embed.set_footer(text=f"ID: {context.player_data.get('id')}")
    return embed


def _set_mapper_author(
    embed: discord.Embed, player_data: dict[str, Any], user_id_for_l10n: int
) -> None:
    user_id = player_data.get("id")
    avatar_url = player_data.get("avatar_url")
    embed.set_author(
        name=_mapper_title(player_data.get("username", "N/A"), user_id_for_l10n),
        url=f"https://osu.ppy.sh/users/{user_id}" if user_id else None,
        icon_url=str(avatar_url) if avatar_url else None,
    )


def _mapper_title(username: str, user_id_for_l10n: int) -> str:
    fallback = f"{username}'s Mapping Stats"
    template = lstr(user_id_for_l10n, "mapper_stats_embed_title", "mapper_stats_embed_title")
    if template == "mapper_stats_embed_title" or "{}" not in template:
        return fallback
    if "LSTR_KEY_ERROR" in template or "<translation_missing" in template:
        return fallback
    try:
        return template.format(username)
    except (IndexError, KeyError, ValueError) as exc:
        logger.opt(exception=exc).error(f"Formatting localized mapper title '{template}' failed.")
        return fallback


def _add_mapper_stats_fields(embed: discord.Embed, context: MapperRenderContext) -> None:
    stats = context.stats
    formatter = context.formatter
    user_id_for_l10n = context.user_id_for_l10n
    field_specs = (
        ("mapper_total_sets", str(stats.total_mapsets), True),
        ("mapper_ranked_loved", str(stats.ranked_loved_sets), True),
        (
            "mapper_guest_difficulties",
            _optional_count(stats.guest_diffs_count, formatter, user_id_for_l10n),
            True,
        ),
        ("mapper_first_upload", _first_upload_text(stats, formatter, user_id_for_l10n), True),
        (
            "mapper_mapping_duration",
            _mapping_duration_text(stats, formatter, user_id_for_l10n),
            True,
        ),
        ("mapper_total_favourites", f"{stats.total_favourites:,}", True),
        (
            "mapper_followers",
            _optional_count(stats.followers_count, formatter, user_id_for_l10n),
            True,
        ),
    )
    for key, value, inline in field_specs:
        embed.add_field(
            name=formatter.lstr_or_na(user_id_for_l10n, key), value=value, inline=inline
        )
    embed.add_field(name=ZERO_WIDTH_SPACE, value=ZERO_WIDTH_SPACE, inline=True)
    embed.add_field(
        name=formatter.lstr_or_na(user_id_for_l10n, "mapper_kudosu"),
        value=_optional_count(stats.kudosu_total, formatter, user_id_for_l10n),
        inline=True,
    )
    embed.add_field(name=ZERO_WIDTH_SPACE, value=ZERO_WIDTH_SPACE, inline=False)


def _optional_count(value: Any, formatter: UserFormatter, user_id_for_l10n: int) -> str:
    if value is None:
        return formatter.lstr_or_na(user_id_for_l10n, "value_not_available")
    return f"{value:,}"


def _first_upload_text(stats: MappingStats, formatter: UserFormatter, user_id_for_l10n: int) -> str:
    if stats.earliest_submission_date is None:
        return formatter.lstr_or_na(user_id_for_l10n, "never_uploaded")
    return formatter.datetime_text(stats.earliest_submission_date, user_id_for_l10n)


def _mapping_duration_text(
    stats: MappingStats, formatter: UserFormatter, user_id_for_l10n: int
) -> str:
    if stats.earliest_submission_date is None:
        return formatter.lstr_or_na(user_id_for_l10n, "value_not_available")
    return formatter.time_since(stats.earliest_submission_date, user_id_for_l10n, short=False)


def _add_latest_submission_field(embed: discord.Embed, context: MapperRenderContext) -> None:
    stats = context.stats
    formatter = context.formatter
    user_id_for_l10n = context.user_id_for_l10n
    field_name = formatter.lstr_or_na(user_id_for_l10n, "mapper_latest_submission")
    if stats.latest_beatmapset is None:
        embed.add_field(
            name=field_name,
            value=formatter.lstr_or_na(user_id_for_l10n, "never_uploaded"),
            inline=False,
        )
        return

    embed.add_field(
        name=field_name,
        value=_latest_submission_text(stats, formatter, user_id_for_l10n),
        inline=False,
    )
    if cover_url := _latest_cover_url(stats.latest_beatmapset):
        embed.set_image(url=cover_url)


def _latest_submission_text(
    stats: MappingStats, formatter: UserFormatter, user_id_for_l10n: int
) -> str:
    beatmapset = stats.latest_beatmapset
    if beatmapset is None:
        return formatter.lstr_or_na(user_id_for_l10n, "never_uploaded")

    title = beatmapset.get("title", "Unknown Title")
    artist = beatmapset.get("artist", "Unknown Artist")
    beatmapset_id = beatmapset.get("id")
    label = f"{artist} - {title}"
    if beatmapset_id:
        label = f"[{label}](https://osu.ppy.sh/beatmapsets/{beatmapset_id})"
    if stats.latest_submission_date is None:
        return label
    date_text = formatter.datetime_text(stats.latest_submission_date, user_id_for_l10n)
    return f"{label}\n{date_text}"


def _latest_cover_url(beatmapset: dict[str, Any]) -> str | None:
    covers = beatmapset.get("covers")
    if not isinstance(covers, dict):
        return None
    return covers.get("card") or covers.get("cover")
