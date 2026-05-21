from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from loguru import logger

from utils.beatmap_utils import get_beatmap_status_display
from utils.localization import get_localized_string as lstr

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI

OSU_MODES_DISPLAY = {0: "mode_std", 1: "mode_taiko", 2: "mode_ctb", 3: "mode_mania"}
OSU_STANDARD_RULESET_ID = 0
BEATMAP_EMBED_COLOR = 0xFF69B4

BeatmapData = dict[str, Any]


@dataclass(frozen=True)
class BeatmapQuery:
    beatmap_id: str | None
    beatmapset_id: str | None


@dataclass(frozen=True)
class BeatmapSelection:
    target: BeatmapData
    beatmaps: list[BeatmapData]


@dataclass(frozen=True)
class BeatmapEmbedContext:
    query: BeatmapQuery
    selection: BeatmapSelection
    user_id: int
    beatmapset: BeatmapData

    @property
    def target(self) -> BeatmapData:
        return self.selection.target


class BeatmapCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client
        self.beatmap_url_pattern = re.compile(
            r"https://osu\.ppy\.sh/(?:beatmapsets/(?P<set_id_long>\d+)(?:#(osu|taiko|fruits|mania)/)?(?P<map_id_long>\d+)?|s/(?P<set_id_short>\d+)|b/(?P<map_id_short>\d+)|beatmaps/(?P<map_id_single>\d+))"
        )

    def get_mode_name(self, mode_int: int, user_id: int) -> str:
        key = OSU_MODES_DISPLAY.get(mode_int, "mode_unknown")
        return lstr(user_id, key)

    def format_length(self, total_seconds: int) -> str:
        """將秒數格式化為 mm:ss"""
        if not total_seconds:
            return "0:00"
        try:
            return str(datetime.timedelta(seconds=int(total_seconds)))[2:]
        except ValueError:
            return "N/A"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        match = self.beatmap_url_pattern.search(message.content)
        if not match:
            return

        query = self._query_from_match(match)
        selection = await self._fetch_selection(query)
        if selection is None:
            await self._reply_if_mentioned(message, "beatmap_api_error")
            return

        beatmapset = self._beatmapset_data(selection.target)
        context = BeatmapEmbedContext(query, selection, message.author.id, beatmapset)
        await message.reply(embed=self._build_beatmap_embed(context), mention_author=False)

    def _query_from_match(self, match: re.Match[str]) -> BeatmapQuery:
        beatmap_id = (
            match.group("map_id_long")
            or match.group("map_id_short")
            or match.group("map_id_single")
        )
        beatmapset_id = match.group("set_id_long") or match.group("set_id_short")
        return BeatmapQuery(beatmap_id, beatmapset_id)

    async def _fetch_selection(self, query: BeatmapQuery) -> BeatmapSelection | None:
        beatmaps, direct_beatmap = await self._fetch_candidates(query)
        if not beatmaps:
            return None

        target = self._select_target_beatmap(query, beatmaps, direct_beatmap)
        if target is None:
            return None
        return BeatmapSelection(target, beatmaps)

    async def _fetch_candidates(
        self, query: BeatmapQuery
    ) -> tuple[list[BeatmapData], BeatmapData | None]:
        if query.beatmap_id:
            beatmap = await self.osu_api.get_beatmap_details(beatmap_id=int(query.beatmap_id))
            return [beatmap], beatmap

        if query.beatmapset_id:
            beatmapset = await self.osu_api.get_beatmapset(beatmapset_id=int(query.beatmapset_id))
            return self._beatmaps_from_set(beatmapset), None

        return [], None

    def _beatmaps_from_set(self, beatmapset: BeatmapData) -> list[BeatmapData]:
        beatmaps = beatmapset.get("beatmaps")
        if beatmaps is None:
            return []
        if not isinstance(beatmaps, list) or not all(isinstance(item, dict) for item in beatmaps):
            msg = "beatmapset beatmaps must be a list of objects"
            raise TypeError(msg)
        return beatmaps

    def _select_target_beatmap(
        self, query: BeatmapQuery, beatmaps: list[BeatmapData], direct_beatmap: BeatmapData | None
    ) -> BeatmapData | None:
        if query.beatmap_id:
            if direct_beatmap and str(direct_beatmap.get("id")) == query.beatmap_id:
                return direct_beatmap
            return next(
                (beatmap for beatmap in beatmaps if str(beatmap.get("id")) == query.beatmap_id),
                None,
            )

        return next(
            (
                beatmap
                for beatmap in beatmaps
                if beatmap.get("ruleset_id") == OSU_STANDARD_RULESET_ID
            ),
            beatmaps[0],
        )

    def _beatmapset_data(self, target_beatmap: BeatmapData) -> BeatmapData:
        beatmapset = target_beatmap.get("beatmapset")
        if isinstance(beatmapset, dict):
            return beatmapset

        if beatmapset is not None:
            msg = "beatmapset field must be an object"
            raise TypeError(msg)

        logger.warning(
            f"[BeatmapCog] target_beatmap for id {target_beatmap.get('id')} missing 'beatmapset' field."
        )
        return {}

    async def _reply_if_mentioned(self, message: discord.Message, key: str) -> None:
        if self.bot.user.mentioned_in(message):
            await message.reply(lstr(message.author.id, key), mention_author=False)

    def _build_beatmap_embed(self, context: BeatmapEmbedContext) -> discord.Embed:
        title = context.beatmapset.get("title", "N/A")
        version = context.target.get("version", "N/A")
        beatmap_id = context.target.get("id")
        beatmap_url = context.target.get("url", f"https://osu.ppy.sh/b/{beatmap_id}")

        embed = discord.Embed(
            title=f"{title} [{version}]", url=beatmap_url, color=BEATMAP_EMBED_COLOR
        )
        embed.set_author(name=lstr(context.user_id, "beatmap_embed_title"))
        embed.set_thumbnail(url=self._cover_url(context.beatmapset))
        self._add_identity_fields(embed, context)
        self._add_stat_fields(embed, context)
        self._add_timing_fields(embed, context)
        embed.set_footer(text=self._footer_text(context))
        return embed

    def _cover_url(self, beatmapset: BeatmapData) -> str:
        covers = beatmapset.get("covers")
        if covers is None:
            return discord.Embed.Empty
        if not isinstance(covers, dict):
            msg = "beatmapset covers must be an object"
            raise TypeError(msg)
        return covers.get("card", discord.Embed.Empty)

    def _status_display(self, context: BeatmapEmbedContext) -> str:
        raw_status = context.beatmapset.get("status")
        if not isinstance(raw_status, str):
            raw_status = context.beatmapset.get("ranked", context.beatmapset.get("approved"))
        if raw_status is None:
            raw_status = context.target.get("status")
        if raw_status is not None and not isinstance(raw_status, str):
            raw_status = context.target.get("ranked", context.target.get("approved"))
        return get_beatmap_status_display(raw_status, context.user_id, lstr)

    def _add_identity_fields(self, embed: discord.Embed, context: BeatmapEmbedContext) -> None:
        creator = context.beatmapset.get("creator", "N/A")
        creator_id = context.beatmapset.get("user_id")
        mode_name = self.get_mode_name(int(context.target.get("ruleset_id", 0)), context.user_id)

        embed.add_field(
            name=lstr(context.user_id, "beatmap_creator_label"),
            value=f"[{creator}](https://osu.ppy.sh/u/{creator_id})" if creator_id else creator,
            inline=True,
        )
        embed.add_field(
            name=lstr(context.user_id, "beatmap_status_label"),
            value=f"{self._status_display(context)} ({mode_name})",
            inline=True,
        )

    def _add_stat_fields(self, embed: discord.Embed, context: BeatmapEmbedContext) -> None:
        stats = {
            "cs": float(context.target.get("cs", 0.0)),
            "ar": float(context.target.get("ar", 0.0)),
            "od": float(context.target.get("accuracy", 0.0)),
            "hp": float(context.target.get("drain", 0.0)),
        }
        embed.add_field(
            name=lstr(context.user_id, "beatmap_difficulty_label"),
            value=f"{float(context.target.get('difficulty_rating', 0.0)):.2f} ★",
            inline=True,
        )
        embed.add_field(
            name=lstr(context.user_id, "beatmap_stats_label"),
            value=f"CS: `{stats['cs']}` AR: `{stats['ar']}` OD: `{stats['od']}` HP: `{stats['hp']}`",
            inline=False,
        )

    def _add_timing_fields(self, embed: discord.Embed, context: BeatmapEmbedContext) -> None:
        total_length = int(context.target.get("total_length", 0))
        hit_length = int(context.target.get("hit_length", 0))
        playable_label = lstr(
            context.user_id, "short_playable_time_indicator", default_fallback="play"
        )
        length = f"{self.format_length(total_length)} ({self.format_length(hit_length)} {playable_label})"
        embed.add_field(
            name=lstr(context.user_id, "beatmap_length_label"), value=length, inline=True
        )
        embed.add_field(
            name=lstr(context.user_id, "beatmap_bpm_label"),
            value=f"{float(context.target.get('bpm', 0.0)):.0f}",
            inline=True,
        )
        embed.add_field(
            name=lstr(context.user_id, "beatmap_max_combo_label"),
            value=self._max_combo_text(context.target),
            inline=True,
        )

    def _max_combo_text(self, target_beatmap: BeatmapData) -> str:
        max_combo = target_beatmap.get("max_combo")
        return f"{max_combo}x" if max_combo else "N/A"

    def _footer_text(self, context: BeatmapEmbedContext) -> str:
        beatmap_id = context.target.get("id")
        beatmapset_id = context.target.get("beatmapset_id") or context.beatmapset.get("id")
        footer = (
            f"{lstr(context.user_id, 'beatmap_id_label')}: {beatmap_id} | "
            f"{lstr(context.user_id, 'beatmapset_id_label')}: {beatmapset_id}"
        )
        difficulty_count = self._difficulty_count(context)
        if difficulty_count > 1:
            footer += (
                "\n"
                f"{lstr(context.user_id, 'beatmap_multiple_difficulties_footer', difficulty_count)}"
            )
        return footer

    def _difficulty_count(self, context: BeatmapEmbedContext) -> int:
        if context.query.beatmap_id or not context.query.beatmapset_id:
            return 0
        total = context.beatmapset.get("total")
        if isinstance(total, int):
            return total
        return len(context.selection.beatmaps)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BeatmapCog(bot))
    logger.info("BeatmapCog loaded.")
