from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_localized_string as lstr
from utils.osu_api import RULESET_IDS

from .pp_embed_builder import PpEmbedBuilder, PpEmbedRequest
from .pp_views import ModSelectView, PpViewConfig

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI


BEATMAPSET_URL_RE = re.compile(r"beatmapsets/(\d+)(?:#(osu|taiko|fruits|mania)/(\d+))?")
BEATMAP_SHORT_URL_RE = re.compile(r"osu.ppy.sh/b/(\d+)")
BEATMAPSET_SHORT_URL_RE = re.compile(r"osu.ppy.sh/s/(\d+)")
BEATMAP_MODE_PRIORITY = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}
ERROR_DETAIL_LIMIT = 100


class PpCommandError(Exception):
    def __init__(self, message: str, *, ephemeral: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.ephemeral = ephemeral


@dataclass(frozen=True, kw_only=True)
class BeatmapUrlParts:
    beatmap_id: int | None
    beatmapset_id: int | None


@dataclass(frozen=True, kw_only=True)
class BeatmapSelection:
    beatmap_id: int
    ruleset_id: int
    target_beatmap: dict[str, Any]
    beatmapset_data: dict[str, Any]
    all_maps_in_set: list[dict[str, Any]]
    current_difficulty_index: int


class PpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client
        self.embed_builder = PpEmbedBuilder(osu_api=self.osu_api)

    @app_commands.command(name="pp", description="Shows PP information for an osu! beatmap.")
    @app_commands.describe(
        url="The URL of the osu! beatmap (either beatmapset or specific difficulty)."
    )
    async def pp(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer()
        user_id_for_l10n = interaction.user.id
        try:
            await self._send_pp(interaction, url, user_id_for_l10n)
        except PpCommandError as exc:
            await interaction.followup.send(exc.message, ephemeral=exc.ephemeral)
        except Exception as exc:
            await self._send_unexpected_error(interaction, user_id_for_l10n, exc)

    async def _send_pp(
        self, interaction: discord.Interaction, url: str, user_id_for_l10n: int
    ) -> None:
        selection = await self._resolve_selection(_parse_beatmap_url(url), user_id_for_l10n)
        attributes = await self._get_initial_attributes(selection, user_id_for_l10n)
        result = await self.embed_builder.create(
            _embed_request(selection, attributes, user_id_for_l10n)
        )
        view = self._view(selection, user_id_for_l10n)
        await interaction.followup.send(embed=result.embed, view=view)
        await self._send_rosu_error(interaction, user_id_for_l10n, result.rosu_error_key)

    async def _resolve_selection(
        self, url_parts: BeatmapUrlParts, user_id_for_l10n: int
    ) -> BeatmapSelection:
        beatmapset_id = await self._resolve_beatmapset_id(url_parts, user_id_for_l10n)
        beatmapset_data = await self._get_beatmapset_or_error(beatmapset_id, user_id_for_l10n)
        sorted_maps = _sorted_beatmaps(beatmapset_data, user_id_for_l10n)
        difficulty_index = _resolve_difficulty_index(sorted_maps, url_parts.beatmap_id)
        target_beatmap = sorted_maps[difficulty_index]
        beatmap_id = _require_beatmap_id(target_beatmap, user_id_for_l10n)
        return BeatmapSelection(
            beatmap_id=beatmap_id,
            ruleset_id=RULESET_IDS.get(target_beatmap.get("mode"), 0),
            target_beatmap=target_beatmap,
            beatmapset_data=beatmapset_data,
            all_maps_in_set=sorted_maps,
            current_difficulty_index=difficulty_index,
        )

    async def _resolve_beatmapset_id(
        self, url_parts: BeatmapUrlParts, user_id_for_l10n: int
    ) -> int:
        if url_parts.beatmapset_id is not None:
            return url_parts.beatmapset_id
        if url_parts.beatmap_id is None:
            raise _command_error(
                user_id_for_l10n, "error_invalid_beatmap_url", "Invalid osu! beatmap URL format."
            )

        details = await self.osu_api.get_beatmap_details(beatmap_id=url_parts.beatmap_id)
        beatmapset_id = details.get("beatmapset_id")
        if isinstance(beatmapset_id, int):
            return beatmapset_id

        raise _command_error(
            user_id_for_l10n,
            "error_beatmap_data_incomplete",
            "Could not retrieve beatmapset ID for the given difficulty.",
        )

    async def _get_beatmapset_or_error(
        self, beatmapset_id: int, user_id_for_l10n: int
    ) -> dict[str, Any]:
        beatmapset_data = await self.osu_api.get_beatmapset(beatmapset_id=beatmapset_id)
        if isinstance(beatmapset_data.get("beatmaps"), list):
            return beatmapset_data

        raise _command_error(
            user_id_for_l10n,
            "error_beatmapset_not_found_api",
            "Could not find the specified beatmapset or it has no maps.",
        )

    async def _get_initial_attributes(
        self, selection: BeatmapSelection, user_id_for_l10n: int
    ) -> dict[str, Any]:
        attributes = await self.osu_api.get_beatmap_attributes(
            beatmap_id=selection.beatmap_id, mods=[], ruleset_id=selection.ruleset_id
        )
        if isinstance(attributes.get("attributes"), dict):
            return attributes

        raise _command_error(
            user_id_for_l10n,
            "error_beatmap_attributes_not_found",
            "Could not retrieve initial beatmap attributes.",
        )

    def _view(self, selection: BeatmapSelection, user_id_for_l10n: int) -> ModSelectView:
        return ModSelectView(
            PpViewConfig(
                osu_api=self.osu_api,
                embed_builder=self.embed_builder,
                rosu_error_notifier=self._send_rosu_error,
                beatmap_id=selection.beatmap_id,
                current_ruleset_id=selection.ruleset_id,
                target_beatmap=selection.target_beatmap,
                beatmapset_data=selection.beatmapset_data,
                user_id_for_l10n=user_id_for_l10n,
                all_maps_in_set=selection.all_maps_in_set,
                current_difficulty_index=selection.current_difficulty_index,
            )
        )

    async def _send_rosu_error(
        self, interaction: discord.Interaction, user_id_for_l10n: int, error_key: str | None
    ) -> None:
        if error_key is None:
            return
        if interaction.is_expired():
            logger.warning(f"[PpCog] Interaction expired, cannot send rosu-pp error: {error_key}")
            return

        await interaction.followup.send(
            lstr(user_id_for_l10n, error_key, "An error occurred during local PP calculation."),
            ephemeral=True,
        )

    async def _send_unexpected_error(
        self, interaction: discord.Interaction, user_id_for_l10n: int, exc: Exception
    ) -> None:
        logger.opt(exception=exc).error("[PpCog] Error in /pp command")
        await interaction.followup.send(
            lstr(
                user_id_for_l10n,
                "error_generic_command",
                "An unexpected error occurred while executing the command: {}",
                _error_detail(exc),
            )
        )


def _parse_beatmap_url(url: str) -> BeatmapUrlParts:
    if match := BEATMAPSET_URL_RE.search(url):
        return BeatmapUrlParts(
            beatmapset_id=int(match.group(1)),
            beatmap_id=int(match.group(3)) if match.group(3) else None,
        )
    if match := BEATMAP_SHORT_URL_RE.search(url):
        return BeatmapUrlParts(beatmap_id=int(match.group(1)), beatmapset_id=None)
    if match := BEATMAPSET_SHORT_URL_RE.search(url):
        return BeatmapUrlParts(beatmap_id=None, beatmapset_id=int(match.group(1)))

    raise _command_error(None, "error_invalid_beatmap_url", "Invalid osu! beatmap URL format.")


def _sorted_beatmaps(
    beatmapset_data: dict[str, Any], user_id_for_l10n: int
) -> list[dict[str, Any]]:
    raw_beatmaps = beatmapset_data.get("beatmaps", [])
    beatmaps = _expect_beatmap_list(raw_beatmaps)
    if not beatmaps:
        raise _command_error(
            user_id_for_l10n, "error_no_maps_in_set", "Beatmapset contains no difficulties."
        )
    return sorted(beatmaps, key=_beatmap_sort_key)


def _expect_beatmap_list(raw_beatmaps: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_beatmaps, list):
        msg = "beatmapset payload beatmaps field must be a list"
        raise TypeError(msg)
    if not all(isinstance(beatmap, dict) for beatmap in raw_beatmaps):
        msg = "beatmapset payload beatmaps field contains non-object entries"
        raise TypeError(msg)
    return raw_beatmaps


def _beatmap_sort_key(beatmap: dict[str, Any]) -> tuple[int, float]:
    return (
        BEATMAP_MODE_PRIORITY.get(beatmap.get("mode"), len(BEATMAP_MODE_PRIORITY)),
        float(beatmap.get("difficulty_rating", 0)),
    )


def _resolve_difficulty_index(beatmaps: list[dict[str, Any]], beatmap_id: int | None) -> int:
    if beatmap_id is None:
        return 0
    for index, beatmap in enumerate(beatmaps):
        if beatmap.get("id") == beatmap_id:
            return index

    logger.warning(
        f"[PpCog] beatmap_id {beatmap_id} not found in its beatmapset. Defaulting to index 0."
    )
    return 0


def _require_beatmap_id(beatmap: dict[str, Any], user_id_for_l10n: int) -> int:
    beatmap_id = beatmap.get("id")
    if isinstance(beatmap_id, int):
        return beatmap_id
    raise _command_error(
        user_id_for_l10n,
        "error_beatmap_data_incomplete",
        "Could not retrieve complete beatmap data.",
    )


def _embed_request(
    selection: BeatmapSelection, attributes: dict[str, Any], user_id_for_l10n: int
) -> PpEmbedRequest:
    return PpEmbedRequest(
        target_beatmap=selection.target_beatmap,
        beatmapset_data=selection.beatmapset_data,
        beatmap_attributes_response=attributes,
        user_id_for_l10n=user_id_for_l10n,
        selected_mods=[],
    )


def _command_error(user_id_for_l10n: int | None, key: str, fallback: str) -> PpCommandError:
    return PpCommandError(lstr(user_id_for_l10n, key, fallback))


def _error_detail(exc: Exception) -> str:
    detail = str(exc)
    return detail if len(detail) <= ERROR_DETAIL_LIMIT else f"{detail[:ERROR_DETAIL_LIMIT]}..."


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PpCog(bot))
    logger.info("PpCog loaded.")
