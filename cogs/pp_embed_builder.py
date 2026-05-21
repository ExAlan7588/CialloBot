from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from utils import beatmap_utils
from utils.beatmap_utils import get_beatmap_status_display
from utils.localization import get_localized_string as lstr

from .osu_formatting import format_mods_for_display

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from utils.osu_api import OsuAPI


@dataclass(frozen=True, kw_only=True)
class PpEmbedRequest:
    target_beatmap: dict[str, Any]
    beatmapset_data: dict[str, Any]
    beatmap_attributes_response: dict[str, Any]
    user_id_for_l10n: int
    selected_mods: list[str]


@dataclass(frozen=True, kw_only=True)
class PpEmbedResult:
    embed: discord.Embed
    rosu_error_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class BeatmapDisplayData:
    artist: str
    title: str
    version: str
    mode: str
    cs: Any
    ar: Any
    hp: Any
    od: Any
    stars: Any
    pp_100: Any
    max_combo: Any
    used_rosu_pp: bool = False
    rosu_error_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class PpEmbedBuilder:
    osu_api: OsuAPI

    async def create(self, request: PpEmbedRequest) -> PpEmbedResult:
        display_data = _initial_display_data(request)
        if display_data.pp_100 is None:
            display_data = await self._with_rosu_pp(request, display_data)

        embed = _build_embed(request, display_data)
        return PpEmbedResult(embed=embed, rosu_error_key=display_data.rosu_error_key)

    async def _with_rosu_pp(
        self, request: PpEmbedRequest, display_data: BeatmapDisplayData
    ) -> BeatmapDisplayData:
        session = self._session_for_download()
        beatmap_id = request.target_beatmap.get("id")
        if session is None or not isinstance(beatmap_id, int):
            logger.warning(
                "[PpCog] Cannot run rosu-pp because session or beatmap id is unavailable."
            )
            return _display_with_rosu_error(display_data, "error_rosupp_unexpected")

        logger.debug(
            f"[PpCog] API did not return PP. Attempting rosu-pp for beatmap ID: {beatmap_id}"
        )
        return await _calculate_rosu_display_data(request, display_data, session, beatmap_id)

    def _session_for_download(self) -> ClientSession | None:
        session = getattr(self.osu_api, "session", None)
        if session is None or session.closed:
            return None
        return session


def _initial_display_data(request: PpEmbedRequest) -> BeatmapDisplayData:
    attrs = request.beatmap_attributes_response.get("attributes", {})
    target = request.target_beatmap
    return BeatmapDisplayData(
        artist=request.beatmapset_data.get("artist", "Unknown Artist"),
        title=request.beatmapset_data.get("title", "Unknown Title"),
        version=target.get("version", "Unknown Difficulty"),
        mode=target.get("mode", "osu"),
        cs=_attribute_or_beatmap_value(attrs, target, "circle_size", "cs"),
        ar=_attribute_or_beatmap_value(attrs, target, "approach_rate", "ar"),
        hp=_attribute_or_beatmap_value(attrs, target, "hp_drain", "drain"),
        od=_attribute_or_beatmap_value(attrs, target, "accuracy", "accuracy"),
        stars=attrs.get("star_rating", "N/A"),
        pp_100=attrs.get("pp"),
        max_combo=attrs.get("max_combo", target.get("max_combo")),
    )


def _attribute_or_beatmap_value(
    attrs: dict[str, Any], target_beatmap: dict[str, Any], attr_key: str, beatmap_key: str
) -> Any:
    value = attrs.get(attr_key)
    return target_beatmap.get(beatmap_key, "N/A") if value is None else value


async def _calculate_rosu_display_data(
    request: PpEmbedRequest,
    display_data: BeatmapDisplayData,
    session: ClientSession,
    beatmap_id: int,
) -> BeatmapDisplayData:
    osu_file_path: str | None = None
    try:
        osu_file_path = await beatmap_utils.download_osu_file(beatmap_id, session)
        metadata = beatmap_utils.parse_osu_file_metadata(osu_file_path)
        rosu_result = await beatmap_utils.calculate_pp_with_rosu(
            osu_file_path, request.selected_mods, accuracy=100.0, combo=None, misses=0
        )
    except beatmap_utils.BeatmapDownloadError as exc:
        logger.error(f"[PpCog] Error downloading .osu file: {exc}")
        return _display_with_rosu_error(display_data, "error_beatmap_download_failed")
    except beatmap_utils.RosuPpCalculationError as exc:
        logger.error(f"[PpCog] Error calculating PP with rosu-pp: {exc}")
        return _display_with_rosu_error(display_data, "error_rosupp_calculation_failed")
    finally:
        if osu_file_path:
            beatmap_utils.delete_osu_file(osu_file_path)

    logger.debug(
        f"[PpCog] rosu-pp calculated: PP={rosu_result.get('pp')}, Stars={rosu_result.get('stars')}"
    )
    return BeatmapDisplayData(
        artist=metadata.get("artist", display_data.artist),
        title=metadata.get("title", display_data.title),
        version=metadata.get("version", display_data.version),
        mode=display_data.mode,
        cs=display_data.cs,
        ar=display_data.ar,
        hp=display_data.hp,
        od=display_data.od,
        stars=rosu_result.get("stars"),
        pp_100=rosu_result.get("pp"),
        max_combo=rosu_result.get("max_combo"),
        used_rosu_pp=True,
    )


def _display_with_rosu_error(
    display_data: BeatmapDisplayData, error_key: str
) -> BeatmapDisplayData:
    return BeatmapDisplayData(
        artist=display_data.artist,
        title=display_data.title,
        version=display_data.version,
        mode=display_data.mode,
        cs=display_data.cs,
        ar=display_data.ar,
        hp=display_data.hp,
        od=display_data.od,
        stars=display_data.stars,
        pp_100=display_data.pp_100,
        max_combo=display_data.max_combo,
        used_rosu_pp=display_data.used_rosu_pp,
        rosu_error_key=error_key,
    )


def _build_embed(request: PpEmbedRequest, display_data: BeatmapDisplayData) -> discord.Embed:
    embed = discord.Embed(
        title=_embed_title(request, display_data),
        url=request.target_beatmap.get("url"),
        color=discord.Color.blue(),
    )
    _set_cover(embed, request.beatmapset_data)
    if display_data.used_rosu_pp:
        embed.set_footer(text="PP via rosu-pp")

    _add_status_field(embed, request)
    _add_attributes_field(embed, request, display_data)
    _add_map_info_field(embed, request, display_data)
    _add_pp_field(embed, request, display_data)
    return embed


def _embed_title(request: PpEmbedRequest, display_data: BeatmapDisplayData) -> str:
    mods = format_mods_for_display(request.selected_mods)
    return f"{display_data.artist} - {display_data.title} [{display_data.version}] {mods}".strip()


def _set_cover(embed: discord.Embed, beatmapset_data: dict[str, Any]) -> None:
    cover_url = beatmapset_data.get("covers", {}).get("cover")
    if cover_url:
        embed.set_image(url=cover_url)


def _add_status_field(embed: discord.Embed, request: PpEmbedRequest) -> None:
    status_display = get_beatmap_status_display(
        _raw_beatmap_status(request.beatmapset_data), request.user_id_for_l10n, lstr
    )
    embed.add_field(
        name=lstr(request.user_id_for_l10n, "pp_embed_beatmap_status", "Beatmap Status"),
        value=status_display,
        inline=False,
    )


def _raw_beatmap_status(beatmapset_data: dict[str, Any]) -> str | int | None:
    raw_status = beatmapset_data.get("status")
    return raw_status if isinstance(raw_status, str) else beatmapset_data.get("ranked")


def _add_attributes_field(
    embed: discord.Embed, request: PpEmbedRequest, display_data: BeatmapDisplayData
) -> None:
    embed.add_field(
        name=lstr(request.user_id_for_l10n, "pp_embed_attributes", "Attributes"),
        value=_attributes_line(display_data),
        inline=False,
    )


def _attributes_line(display_data: BeatmapDisplayData) -> str:
    cs, ar, prefix = _mode_adjusted_cs_ar(display_data)
    return f"{prefix}CS: `{cs}` AR: `{ar}` HP: `{display_data.hp}` OD: `{display_data.od}`".strip()


def _mode_adjusted_cs_ar(display_data: BeatmapDisplayData) -> tuple[Any, Any, str]:
    if display_data.mode == "taiko":
        return "N/A", "N/A", ""
    if display_data.mode == "mania":
        return "N/A", "N/A", f"Key: `{display_data.cs}` "
    return display_data.cs, display_data.ar, ""


def _add_map_info_field(
    embed: discord.Embed, request: PpEmbedRequest, display_data: BeatmapDisplayData
) -> None:
    parts = [
        f"Length: `{_formatted_length(request.target_beatmap)}`",
        f"BPM: `{request.target_beatmap.get('bpm', 'N/A')}`",
        f"Stars: `{_format_stars(display_data.stars)}`",
    ]
    embed.add_field(
        name=lstr(request.user_id_for_l10n, "pp_embed_map_info", "Map Info"),
        value=" ".join(parts),
        inline=False,
    )


def _formatted_length(target_beatmap: dict[str, Any]) -> str:
    length_seconds = int(target_beatmap.get("total_length", 0) or 0)
    minutes = length_seconds // 60
    seconds = length_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _format_stars(stars: Any) -> str:
    return f"{stars:.2f}★" if isinstance(stars, (int, float)) else f"{stars}★"


def _add_pp_field(
    embed: discord.Embed, request: PpEmbedRequest, display_data: BeatmapDisplayData
) -> None:
    field_name = lstr(request.user_id_for_l10n, "pp_100_percent", "PP (100%)")
    if display_data.used_rosu_pp:
        field_name = (
            f"{field_name} {lstr(request.user_id_for_l10n, 'pp_estimated_suffix', '(估算值)')}"
        )
    embed.add_field(
        name=field_name, value=f"`{_format_pp(request, display_data.pp_100)}`", inline=False
    )


def _format_pp(request: PpEmbedRequest, pp_value: Any) -> str:
    if isinstance(pp_value, (int, float)):
        return f"{pp_value:.2f}pp"
    return lstr(request.user_id_for_l10n, "pp_value_not_available", "N/A")
