from __future__ import annotations

import datetime  # 用於轉換時長
import re  # 用於正則表達式解析 URL
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from loguru import logger

# from utils.osu_api_utils import get_ruleset_id_from_string, RateLimiter, get_user_id_for_l10n_from_message # REMOVED
from utils.beatmap_utils import get_beatmap_status_display  # IMPORT THE NEW FUNCTION
from utils.localization import get_localized_string as lstr

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI

# osu! 遊戲模式的映射 (與 osu_cog.py 中的類似，但這裡也需要用到)
OSU_MODES_DISPLAY = {0: "mode_std", 1: "mode_taiko", 2: "mode_ctb", 3: "mode_mania"}


class BeatmapCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client
        # self.rate_limiter = RateLimiter(calls=20, period=60) # Example limits # COMMENTED OUT

        # 正則表達式用於提取 osu! 譜面 ID
        # 匹配 /b/id, /beatmaps/id, /s/set_id, /beatmapsets/set_id, /beatmapsets/set_id#mode/id
        self.beatmap_url_pattern = re.compile(
            r"https://osu\.ppy\.sh/(?:beatmapsets/(?P<set_id_long>\d+)(?:#(osu|taiko|fruits|mania)/)?(?P<map_id_long>\d+)?|s/(?P<set_id_short>\d+)|b/(?P<map_id_short>\d+)|beatmaps/(?P<map_id_single>\d+))"
        )

    def get_mode_name(self, mode_int: int, user_id: int) -> str:
        key = OSU_MODES_DISPLAY.get(mode_int, "mode_unknown")
        return lstr(user_id, key)

    def format_length(self, total_seconds: int, user_id_for_l10n: int) -> str:
        """將秒數格式化為 mm:ss"""
        if not total_seconds:
            return "0:00"
        try:
            return str(datetime.timedelta(seconds=int(total_seconds)))[2:]  # 去掉小時部分 0:
        except:
            return "N/A"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # 忽略機器人自身的消息
        if message.author.bot:
            return

        # 檢查機器人是否被提及 (不是必要條件，按需調整)
        # if not self.bot.user.mentioned_in(message):
        #     return

        # 從訊息內容中查找 URL
        match = self.beatmap_url_pattern.search(message.content)
        if not match:
            # 如果要求必須提及才觸發，可以在這裡回覆一個提示，例如:
            # if self.bot.user.mentioned_in(message):
            #     await message.reply(lstr(message.author.id, "beatmap_no_url_found"), mention_author=False)
            return

        # 提取 ID
        beatmap_id_str = (
            match.group("map_id_long")
            or match.group("map_id_short")
            or match.group("map_id_single")
        )
        beatmapset_id_str = match.group("set_id_long") or match.group("set_id_short")

        user_id_for_l10n = message.author.id
        beatmap_data_list = []  # Initialize as empty list
        target_beatmap_from_direct_id = None  # Used if beatmap_id_str is present

        if beatmap_id_str:
            try:
                beatmap_id = int(beatmap_id_str)
                beatmap_detail = await self.osu_api.get_beatmap_details(beatmap_id=beatmap_id)
                if beatmap_detail:
                    target_beatmap_from_direct_id = beatmap_detail
                    beatmap_data_list = [
                        beatmap_detail
                    ]  # For consistency if logic iterates this list
                # If beatmap_detail is None, beatmap_data_list remains empty
            except ValueError:
                # Invalid beatmap_id format
                pass  # beatmap_data_list remains empty
        elif beatmapset_id_str:
            try:
                beatmapset_id = int(beatmapset_id_str)
                beatmapset_data = await self.osu_api.get_beatmapset(beatmapset_id=beatmapset_id)
                # beatmapset_data for API v2 contains a 'beatmaps' key with list of difficulties
                if (
                    beatmapset_data
                    and "beatmaps" in beatmapset_data
                    and beatmapset_data["beatmaps"] is not None
                ):
                    beatmap_data_list = beatmapset_data["beatmaps"]
                # If no 'beatmaps' or data is None, beatmap_data_list remains empty
            except ValueError:
                # Invalid beatmapset_id format
                pass  # beatmap_data_list remains empty

        if not beatmap_data_list:  # If list is empty after trying to fetch
            # Consider a more specific localization key like "beatmap_api_error_or_not_found"
            if self.bot.user.mentioned_in(message):
                await message.reply(
                    lstr(user_id_for_l10n, "beatmap_api_error"), mention_author=False
                )
            return

        target_beatmap = None
        # num_diffs_in_set was len(beatmap_data_list) before. It's used for footer.
        # If beatmap_id_str was given, beatmap_data_list has at most 1 item.
        # If beatmapset_id_str was given, beatmap_data_list has all diffs.
        len(beatmap_data_list)

        if beatmap_id_str:  # If URL directly pointed to a specific difficulty
            if (
                target_beatmap_from_direct_id
                and str(target_beatmap_from_direct_id.get("id")) == beatmap_id_str
            ):
                target_beatmap = target_beatmap_from_direct_id
            # Fallback: if somehow target_beatmap_from_direct_id wasn't set or ID mismatched
            # This part of the logic might be redundant if target_beatmap_from_direct_id is reliable
            elif beatmap_data_list:
                for bm in beatmap_data_list:  # Should be a list of one if direct fetch worked
                    if str(bm.get("id")) == beatmap_id_str:  # API v2 beatmap id is 'id'
                        target_beatmap = bm
                        break
            # If beatmap_id_str was provided but target_beatmap is still None,
            # it means the specific map wasn't found or API failed for it.
            # The old code did: if not target_beatmap: target_beatmap = beatmap_data_list[0]
            # This is probably not right if a specific ID was requested and not found.
            # Let's rely on the "if not target_beatmap:" check below.

        elif beatmap_data_list:  # Ensure list is not empty
            # Try to find osu!standard (ruleset_id 0)
            for bm in beatmap_data_list:
                if bm.get("ruleset_id") == 0:  # API v2 uses 'ruleset_id' for mode integer
                    target_beatmap = bm
                    break
            if not target_beatmap:  # If no osu!standard, take the first one in the list
                target_beatmap = beatmap_data_list[0]
            # If beatmap_data_list was empty, target_beatmap remains None

        if not target_beatmap:
            # Consider a more specific localization key like "beatmap_not_found_in_set"
            if self.bot.user.mentioned_in(message):
                await message.reply(
                    lstr(user_id_for_l10n, "beatmap_api_error"), mention_author=False
                )
            return

        # DATA EXTRACTION AND EMBED CREATION - UPDATED FOR API V2

        # Beatmap object (target_beatmap) from API v2 contains:
        # id, beatmapset_id, difficulty_rating, version (diff name), cs, ar, accuracy (OD), drain (HP),
        # bpm, total_length, hit_length, max_combo, status (string), url, ruleset_id.
        # It also contains a nested 'beatmapset' object.

        current_beatmapset_data = target_beatmap.get("beatmapset")  # This should be a nested object
        if not current_beatmapset_data:
            current_beatmapset_data = {}  # Fallback to avoid errors, though this indicates an issue
            logger.warning(
                f"[BeatmapCog] target_beatmap for id {target_beatmap.get('id')} missing 'beatmapset' field."
            )

        title = current_beatmapset_data.get("title", "N/A")
        version = target_beatmap.get("version", "N/A")  # This is the difficulty name
        creator = current_beatmapset_data.get("creator", "N/A")  # Mapper's username
        creator_id = current_beatmapset_data.get("user_id")  # Mapper's user ID

        # Determine status text using the new utility function
        # The status is usually in current_beatmapset_data
        raw_status_on_message = current_beatmapset_data.get(
            "status"
        )  # API v2 string: ranked, loved, qualified, pending, graveyard, wip
        if not isinstance(raw_status_on_message, str):
            # Fallback to 'ranked' field (integer) or 'approved' (integer in older API versions for beatmap object)
            raw_status_on_message = current_beatmapset_data.get(
                "ranked", current_beatmapset_data.get("approved")
            )
            if (
                raw_status_on_message is None and current_beatmap_data
            ):  # Final fallback to beatmap specific status if set status missing
                raw_status_on_message = current_beatmap_data.get("status")
                if not isinstance(raw_status_on_message, str):
                    raw_status_on_message = current_beatmap_data.get(
                        "ranked", current_beatmap_data.get("approved")
                    )

        status_display_string_on_message = get_beatmap_status_display(
            raw_status_on_message, user_id_for_l10n, lstr
        )

        stars = float(target_beatmap.get("difficulty_rating", 0.0))

        cs = float(target_beatmap.get("cs", 0.0))
        ar = float(target_beatmap.get("ar", 0.0))
        od = float(
            target_beatmap.get("accuracy", 0.0)
        )  # 'accuracy' field in beatmap obj is OD for osu!std
        hp = float(target_beatmap.get("drain", 0.0))

        bpm = float(target_beatmap.get("bpm", 0.0))
        total_length = int(target_beatmap.get("total_length", 0))  # in seconds
        hit_length = int(target_beatmap.get("hit_length", 0))  # in seconds
        max_combo = target_beatmap.get("max_combo")  # Can be None

        b_id = target_beatmap.get("id")
        # bs_id can be from target_beatmap.beatmapset_id or from current_beatmapset_data.id
        bs_id = target_beatmap.get("beatmapset_id")
        if not bs_id and current_beatmapset_data:  # Fallback if not directly on beatmap object
            bs_id = current_beatmapset_data.get("id")

        beatmap_url = target_beatmap.get("url", f"https://osu.ppy.sh/b/{b_id}")

        beatmap_cover_url = discord.Embed.Empty
        if current_beatmapset_data and "covers" in current_beatmapset_data:
            beatmap_cover_url = current_beatmapset_data["covers"].get("card", discord.Embed.Empty)

        mode_int = int(target_beatmap.get("ruleset_id", 0))  # ruleset_id is the integer mode
        mode_name = self.get_mode_name(mode_int, user_id_for_l10n)

        # For footer: num_diffs_in_set
        # If beatmap_id_str was given, we are showing one specific diff.
        # If only beatmapset_id_str, then beatmap_data_list contains all diffs from that set.
        # The Beatmapset object (current_beatmapset_data) should have 'total' or 'track_count' or similar
        # Or, if we fetched the full set, len(beatmap_data_list) when beatmapset_id_str was used.

        num_diffs_to_report_in_footer = 0
        if not beatmap_id_str and beatmapset_id_str:  # It was a query for a full beatmapset
            if (
                current_beatmapset_data and "total" in current_beatmapset_data
            ):  # API v2 Beatmapset has 'total' beatmaps
                num_diffs_to_report_in_footer = current_beatmapset_data["total"]
            elif beatmap_data_list:  # Fallback using the length of the fetched list of diffs
                num_diffs_to_report_in_footer = len(beatmap_data_list)
        # If beatmap_id_str was present, we don't show "multiple difficulties" footer usually.

        # 創建 Embed
        embed = discord.Embed(
            title=f"{title} [{version}]",
            url=beatmap_url,
            color=0xFF69B4,  # Pink, or choose based on status
        )
        embed.set_author(name=lstr(user_id_for_l10n, "beatmap_embed_title"))
        embed.set_thumbnail(url=beatmap_cover_url)

        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_creator_label"),
            value=f"[{creator}](https://osu.ppy.sh/u/{creator_id})" if creator_id else creator,
            inline=True,
        )
        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_status_label"),
            value=f"{status_display_string_on_message} ({mode_name})",
            inline=True,
        )

        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_difficulty_label"),
            value=f"{stars:.2f} ★",
            inline=True,
        )

        stats_text = f"CS: `{cs}` AR: `{ar}` OD: `{od}` HP: `{hp}`"
        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_stats_label"), value=stats_text, inline=False
        )

        length_formatted = f"{self.format_length(total_length, user_id_for_l10n)} ({self.format_length(hit_length, user_id_for_l10n)} {lstr(user_id_for_l10n, 'short_playable_time_indicator', default_fallback='play')})"
        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_length_label"), value=length_formatted, inline=True
        )
        embed.add_field(
            name=lstr(user_id_for_l10n, "beatmap_bpm_label"), value=f"{bpm:.0f}", inline=True
        )
        if max_combo:
            embed.add_field(
                name=lstr(user_id_for_l10n, "beatmap_max_combo_label"),
                value=f"{max_combo}x",
                inline=True,
            )
        else:  # Create a placeholder field if max_combo is None or 0
            embed.add_field(
                name=lstr(user_id_for_l10n, "beatmap_max_combo_label"), value="N/A", inline=True
            )

        # 頁腳
        footer_text = f"{lstr(user_id_for_l10n, 'beatmap_id_label')}: {b_id} | {lstr(user_id_for_l10n, 'beatmapset_id_label')}: {bs_id}"
        if not beatmap_id_str and num_diffs_to_report_in_footer > 1:
            footer_text += f"\n{lstr(user_id_for_l10n, 'beatmap_multiple_difficulties_footer', num_diffs_to_report_in_footer)}"
        embed.set_footer(text=footer_text)

        await message.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BeatmapCog(bot))
    logger.info("BeatmapCog loaded.")
