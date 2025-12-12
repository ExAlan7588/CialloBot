from __future__ import annotations

import datetime
import io
from typing import TYPE_CHECKING

import discord
import matplotlib.pyplot as plt
import pycountry  # For converting country codes to names/flags
from dateutil.relativedelta import relativedelta  # For calculating time differences
from discord import app_commands
from discord.ext import commands
from loguru import logger

from private import config
from utils import user_data_manager
from utils.localization import get_localized_string as lstr
from utils.localization import get_user_language

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI

# osu! 遊戲模式的映射 (與其他 cog 類似)
OSU_MODES = {  # Used for display keys in lstr
    0: "mode_std",
    1: "mode_taiko",
    2: "mode_ctb",
    3: "mode_mania",
}

# For converting int mode to API v2 string mode
OSU_MODES_INT_TO_STRING = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}

# Corrected Mode Emoji Mappings
MODE_EMOJI_STRINGS = {
    0: "<:std:1373198119361318932>",
    1: "<:taiko:1373198130006200370>",
    2: "<:ctb:1373198138751320104>",
    3: "<:mania:1373198147056304139>",
}

# New: Fallback text for modes if localized name is problematic, to accompany emoji
MODE_FALLBACK_TEXT = {
    0: "osu!",
    1: "Taiko",
    2: "Catch",
    3: "Mania",
}


# 用於將國家代碼轉換為旗幟 Emoji
def get_country_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "🌍"  # Default globe emoji
    try:
        # 確保是大寫
        country_code = country_code.upper()
        # Regional Indicator Symbol Letter A and B
        # A = 127462 (0x1F1E6), B = 127463 (0x1F1E7)
        # Difference is 0 for A, 1 for B, ..., 25 for Z
        return chr(127397 + ord(country_code[0])) + chr(127397 + ord(country_code[1]))
    except Exception:
        return "🌍"  # Fallback


# 用於獲取國家全名
def get_country_name(country_code: str, lang: str = "en") -> str:
    try:
        country = pycountry.countries.get(alpha_2=country_code.upper())
        if country:
            # pycountry doesn't directly support zh_TW, try 'zh' or fall back to official name
            if lang.startswith("zh") and hasattr(
                country, "common_name"
            ):  # common_name might be better for Chinese
                # Try to get specific chinese name if available, else official
                try:
                    return country.name  # pycountry might have some chinese names in .name for some countries
                except KeyError:
                    pass  # fall through
            return country.name
        return country_code  # Fallback to code if not found
    except Exception:
        return country_code  # Fallback


class UserCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client

    def get_na_value(self, user_id_for_l10n: int) -> str:
        # Attempt to get the localized "value_not_available" string
        potential_na = lstr(
            user_id_for_l10n, "value_not_available", "N/A"
        )  # Default to "N/A" if key missing

        # Check for the specific incorrect placeholder, matching the observed error string exactly
        if (
            "__LSTR_KEY_ERRORuser_profile_title__" in potential_na
        ):  # Corrected: removed underscore after ERROR
            # This is the problematic output from lstr.
            # We override it to the known correct translation for "value_not_available" in zh_TW.
            logger.warning(
                "[USER_COG] lstr returned unexpected placeholder for 'value_not_available' (matched exact error string). Forced to '無法取得'."
            )
            return (
                "無法取得"  # Forcing zh_TW N/A as a temporary fix for the user's case
            )

        # Original checks for other error conditions
        if (
            "<translation_missing" in potential_na
            or "<formatting_error" in potential_na
            or potential_na == "value_not_available"
        ):  # Check if lstr returned the key itself
            # If lstr indicated an error, or returned the key.
            # Fallback to a hardcoded "N/A" (English) as per original logic,
            logger.warning(
                f"[USER_COG] lstr indicated error for 'value_not_available' (not the specific placeholder). Fallback to hardcoded 'N/A'. Original: {potential_na}"
            )
            return "N/A"  # Fallback to English "N/A"

        return potential_na

    def _get_lstr_with_na_fallback(self, user_id_for_l10n: int, key: str, *args) -> str:
        # Provide a very distinct placeholder to see if lstr is failing to find the key.
        placeholder_if_key_truly_missing = f"__LSTR_KEY_ERROR__{key}__"

        # Attempt to get the translation
        raw_translation = lstr(
            user_id_for_l10n, key, placeholder_if_key_truly_missing, *args
        )

        # Check if the placeholder was returned (meaning key was not found by lstr)
        # or if lstr indicated a missing translation or formatting error.
        if (
            raw_translation == placeholder_if_key_truly_missing
            or "<translation_missing" in raw_translation
            or "<formatting_error" in raw_translation
        ):
            return self.get_na_value(
                user_id_for_l10n
            )  # Fallback to "N/A" or its translation
        return raw_translation

    def get_mode_name(self, mode_int: int, user_id_for_l10n: int) -> str:
        logger.debug(
            f"[USER_COG get_mode_name] Called with mode_int: {mode_int}, user_id: {user_id_for_l10n}"
        )

        l10n_key = OSU_MODES.get(mode_int, "mode_unknown")
        localized_name = self._get_lstr_with_na_fallback(user_id_for_l10n, l10n_key)

        # If localized name is N/A or key is unknown, try to use a more generic English fallback
        if (
            localized_name == self.get_na_value(user_id_for_l10n)
            or l10n_key == "mode_unknown"
        ):
            base_name = MODE_FALLBACK_TEXT.get(
                mode_int,
                self._get_lstr_with_na_fallback(user_id_for_l10n, "mode_unknown"),
            )
            final_display_name = base_name
        else:
            final_display_name = localized_name

        logger.debug(f"[USER_COG get_mode_name] Result: {final_display_name}")
        return final_display_name

    def format_datetime_obj(
        self,
        dt_obj: datetime.datetime,
        user_id_for_l10n: int,
        format_key: str = "date_format",
    ) -> str:
        if not dt_obj:
            return "N/A"  # Should use self.get_na_value(user_id_for_l10n) ideally
        try:
            # Get the localized format string
            format_str = lstr(
                user_id_for_l10n, format_key, ""
            )  # Pass empty string to get format itself
            # Fallback to ISO-like format if localized format is missing or problematic
            if (
                not format_str
                or "<translation_missing" in format_str
                or "<formatting_error" in format_str
                or format_str == format_key
            ):
                format_str = "%Y-%m-%d %H:%M:%S"
            return dt_obj.strftime(format_str.strip())
        except Exception as e:
            logger.error(
                f"[USER_COG format_datetime_obj] Error formatting datetime: {e}"
            )
            return str(dt_obj)  # Fallback to simple string conversion

    def time_since(
        self, dt_obj: datetime.datetime, user_id_for_l10n: int, short: bool = True
    ) -> str:
        if not dt_obj:
            # For mapper duration, "never_uploaded" is used. For profile join date, this path isn't hit if date missing.
            return lstr(user_id_for_l10n, "never_uploaded", "Never")

        now = datetime.datetime.now(datetime.UTC)
        if dt_obj.tzinfo is None:  # Ensure dt_obj is timezone-aware
            dt_obj = dt_obj.replace(tzinfo=datetime.UTC)

        diff = relativedelta(now, dt_obj)

        # List of potential components with their values, localization keys, and English defaults
        potential_components = [
            {"value": diff.years, "unit_key": "unit_year", "default_unit": "y"},
            {"value": diff.months, "unit_key": "unit_month", "default_unit": "m"},
            {"value": diff.days, "unit_key": "unit_day", "default_unit": "d"},
        ]

        formatted_parts = []
        for comp in potential_components:
            if comp["value"] > 0:
                unit_str = lstr(
                    user_id_for_l10n, comp["unit_key"], comp["default_unit"]
                )
                formatted_parts.append(f"{comp['value']}{unit_str}")

        # Handle seconds if no other larger units were added, or if all are zero until seconds
        if not formatted_parts:
            seconds_value = max(diff.seconds, 0)
            unit_str = lstr(user_id_for_l10n, "unit_second", "s")
            # If not short and we fell through to seconds, it means Y,M,D,H,M were 0.
            # Per request, if not short, minimum is day. If YMD are 0, show "0d" or localized equivalent.
            if not short:
                day_unit_str = lstr(user_id_for_l10n, "unit_day", "d")
                return f"0{day_unit_str}"
            return f"{seconds_value}{unit_str}"

        if short:
            return formatted_parts[0]
        to_join = formatted_parts[:2]
        # If only one part (e.g. "5日") because Y/M were 0, formatted_parts will have 1 element.
        # If Y/M/D were all 0, it would have hit the `if not formatted_parts:` block above and returned "0d".

        lang_code = lstr(user_id_for_l10n, "_lang_code", "en")
        if lang_code.startswith("zh"):
            return "".join(to_join)
        return " ".join(to_join)

    def _build_profile_detail_section(
        self,
        player_data,
        mode_stats,
        user_id_for_l10n,
        current_mode_int: int,
        has_rank_graph: bool = False,
    ):
        # Emoji IDs
        TREE = "<:tree:1373314005116125266>"
        END = "<:end:1373314035373707445>"
        BLACK_CIRCLE = "<a:crownlightblue:1374003894346317824>"  # User updated Emoji ID
        # 成績用 emoji
        EMOJI_SSH = "<:rkhdfl:1373246417350561844>"
        EMOJI_SS = "<:rkss:1373246926379679836>"
        EMOJI_SH = "<:rkshdfl:1373964175671427143>"
        EMOJI_S = "<:rks:1373246734079230072>"
        EMOJI_A = "<:rka:1373246979211132988>"
        # 欄位本地化

        def l(k, *a):
            return self._get_lstr_with_na_fallback(user_id_for_l10n, k, *a)
        na = self.get_na_value(user_id_for_l10n)

        lines = []
        # 新增：遊戲模式顯示
        mode_emoji = MODE_EMOJI_STRINGS.get(current_mode_int, "")
        mode_name = self.get_mode_name(current_mode_int, user_id_for_l10n)
        game_mode_label = l("user_profile_game_mode", "Game Mode")
        lines.extend((f"**{game_mode_label}:** {mode_emoji} {mode_name}", ""))  # Add a blank line for spacing

        # 1. Status 區塊
        # Variable definitions (most are already in place, ensure all needed are here before building status_item_lines)
        country_code = player_data.get("country_code", "")
        country_flag = get_country_flag_emoji(country_code)
        pp_rank = mode_stats.get("global_rank") if mode_stats else None
        pp_country_rank = mode_stats.get("country_rank") if mode_stats else None
        rank_str = f"`#{pp_rank:,}`" if pp_rank is not None else na
        country_rank_str = (
            f"{country_flag} `#{pp_country_rank:,}`"
            if pp_country_rank is not None
            else na
        )

        level = mode_stats.get("level", {}) if mode_stats else {}
        level_current_val = level.get("current")
        level_progress_val = level.get("progress", 0)
        level_str = (
            f"`{level_current_val} + {level_progress_val:.2f}%`"
            if level_current_val is not None
            else na
        )

        pp = mode_stats.get("pp") if mode_stats else None
        acc = mode_stats.get("hit_accuracy") if mode_stats else None
        pp_str = f"`{pp:,.2f}`" if pp is not None else na
        acc_str = f"`{acc:,.2f}%`" if acc is not None else na

        grade_counts = player_data.get("statistics", {}).get("grade_counts", {})
        ssh = grade_counts.get("ssh", 0)
        ss = grade_counts.get("ss", 0)
        sh = grade_counts.get("sh", 0)
        s = grade_counts.get("s", 0)
        a = grade_counts.get("a", 0)
        grades = f"{EMOJI_SSH} `{ssh}` {EMOJI_SS} `{ss}` {EMOJI_SH} `{sh}` {EMOJI_S} `{s}` {EMOJI_A} `{a}`"

        playcount = mode_stats.get("play_count") if mode_stats else None
        playcount_str = f"`{playcount:,}`" if playcount is not None else na

        total_score = mode_stats.get("total_score") if mode_stats else None
        total_score_display = f"`{total_score:,}`" if total_score is not None else na
        avg_score_val = None
        if total_score and playcount and playcount > 0:
            avg_score_val = total_score / playcount
        avg_score_display = (
            f"`{avg_score_val:,.2f}`" if avg_score_val is not None else na
        )

        ranked_score = mode_stats.get("ranked_score") if mode_stats else None
        ranked_score_display = f"`{ranked_score:,}`" if ranked_score is not None else na
        avg_ranked_val = None
        if ranked_score and playcount and playcount > 0:
            avg_ranked_val = ranked_score / playcount
        avg_ranked_display = (
            f"`{avg_ranked_val:,.2f}`" if avg_ranked_val is not None else na
        )

        total_hits = mode_stats.get("total_hits") if mode_stats else None
        total_hits_display = f"`{total_hits:,}`" if total_hits is not None else na
        avg_hits_val = None
        if total_hits and playcount and playcount > 0:
            avg_hits_val = total_hits / playcount
        avg_hits_display = f"`{avg_hits_val:,.2f}`" if avg_hits_val is not None else na

        max_combo = mode_stats.get("maximum_combo") if mode_stats else None
        max_combo_str = f"`{max_combo}`" if max_combo is not None else na

        replays = mode_stats.get("replays_watched_by_others") if mode_stats else None
        replays_str = f"`{replays}`" if replays is not None else na

        status_item_lines = []
        # Order based on user request
        status_item_lines.extend((f"**{l('user_profile_global_rank')}:** {rank_str} ({country_rank_str})", f"**{l('user_profile_level')}:** {level_str}", f"**PP:** {pp_str} {l('user_profile_accuracy')}: {acc_str}", f"**{l('user_profile_grades')}:** {grades}", f"**{l('user_profile_accuracy')}:** {acc_str}", f"**{l('user_profile_play_count')}:** {playcount_str}", f"**{l('user_profile_total_score')}:** {total_score_display}", f"**{l('user_profile_avg_score', 'Avg. Score')}:** {avg_score_display}/{l('user_profile_play_short', 'Play')}", f"**{l('user_profile_ranked_score')}:** {ranked_score_display}", f"**{l('user_profile_avg_ranked_score', 'Avg. Ranked Score')}:** {avg_ranked_display}/{l('user_profile_play_short', 'Play')}", f"**{l('user_profile_total_hits')}:** {total_hits_display}", f"**{l('user_profile_avg_hits', 'Avg. Hits')}:** {avg_hits_display}/{l('user_profile_play_short', 'Play')}", f"**{l('user_profile_max_combo')}:** {max_combo_str}", f"**{l('user_profile_replays_watched')}:** {replays_str}"))

        lines.append(f"{BLACK_CIRCLE} {l('profile_section_status') or 'Status'}")
        for i, item_content in enumerate(status_item_lines):
            prefix = END if i == len(status_item_lines) - 1 else TREE
            lines.append(f"{prefix} {item_content}")

        # 2. 其他區塊
        lines.append(f"\n{BLACK_CIRCLE} {l('profile_section_other') or '其他'}")
        # 以前的名字
        prev_names = player_data.get("previous_usernames")
        prev_names_str = (
            ", ".join(prev_names) if prev_names else na
        )  # Not numerical, no backticks
        lines.append(f"{TREE} **{l('user_profile_previous_names')}:** {prev_names_str}")
        # 好友/追蹤者
        followers = player_data.get("follower_count")
        followers_str = f"`{followers}`" if followers is not None else na
        lines.append(f"{TREE} **{l('user_profile_followers')}:** {followers_str}")
        # 慣用
        playstyle = player_data.get("playstyle")
        playstyle_str = (
            ", ".join(playstyle) if playstyle else na
        )  # Not numerical, no backticks
        lines.append(f"{TREE} **{l('user_profile_playstyle')}:** {playstyle_str}")
        # 成就
        achievements_raw = player_data.get("user_achievements")
        logger.debug(
            f"[USER_COG _build_profile_detail_section] Raw achievements data: {achievements_raw}"
        )
        achievements_str = (
            f"`{len(achievements_raw)}`" if achievements_raw is not None else na
        )
        lines.append(f"{TREE} **{l('user_profile_achievements')}:** {achievements_str}")
        # 總遊玩時間
        total_seconds = mode_stats.get("play_time") if mode_stats else None
        if total_seconds:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            playtime_str = f"`{hours}h {minutes}m`"
        else:
            playtime_str = na
        lines.append(f"{TREE} **{l('user_profile_total_playtime')}:** {playtime_str}")
        # 註冊時間
        join_date_api_val = player_data.get("join_date")
        join_date_display_str = na  # Default to N/A
        if join_date_api_val:
            try:
                join_dt_obj = datetime.datetime.fromisoformat(
                    join_date_api_val
                )
                formatted_date = self.format_datetime_obj(join_dt_obj, user_id_for_l10n)
                relative_time = self.time_since(
                    join_dt_obj, user_id_for_l10n
                )  # short=True by default
                logger.debug(
                    f"Join date: Formatted='{formatted_date}', Relative='{relative_time}'"
                )
                if (
                    formatted_date
                    and relative_time
                    and relative_time != self.get_na_value(user_id_for_l10n)
                ):
                    join_date_display_str = f"{formatted_date} ({relative_time})"
                else:
                    join_date_display_str = formatted_date  # Fallback to just date if relative time is weird
            except Exception as e:
                logger.warning(
                    f"Could not parse or format join_date for detail view: {join_date_api_val}. Error: {e}"
                )
                join_date_display_str = join_date_api_val  # Fallback to raw string from API if parsing/formatting fails

        lines.append(
            f"{END} **{l('user_profile_join_date')}:** {join_date_display_str}"
        )

        # 個人連結 - New Independent Section
        link_detail_lines = []
        twitter_username = player_data.get("twitter")
        if twitter_username:
            link_detail_lines.append(
                f"Twitter: [{twitter_username}](https://x.com/{twitter_username})"
            )

        discord_contact = player_data.get("discord")
        if discord_contact:
            link_detail_lines.append(f"Discord: {discord_contact}")

        if link_detail_lines:  # Only add the "Links" section if there are any links
            lines.append(
                f"\n{BLACK_CIRCLE} **{l('user_profile_links')}:**"
            )  # Using existing key "user_profile_links" as section title

            num_link_details = len(link_detail_lines)
            for i, detail_line_content in enumerate(link_detail_lines):
                prefix_emoji = END if (i == num_link_details - 1) else TREE
                lines.append(f"{prefix_emoji} {detail_line_content}")

        # 3. 圖表區塊 - 動態生成
        if has_rank_graph:  # Only show graph section if rank graph exists
            lines.append(
                f"\n{BLACK_CIRCLE} **{l('user_profile_rank_graph')}:**"
            )  # Changed graph section header

        return "\n".join(lines)

    @app_commands.command(name="profile", description="Shows a user's osu! profile.")
    @app_commands.describe(
        osu_user="osu! username (optional)",
        osu_id="osu! user ID (optional)",
        mode="Game mode (0:std, 1:taiko, 2:ctb, 3:mania). Defaults to user's or server's default.",
        detail="Show detailed profile info (optional)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="STD", value=0),
            app_commands.Choice(name="Taiko", value=1),
            app_commands.Choice(name="CTB", value=2),
            app_commands.Choice(name="Mania", value=3),
        ]
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        osu_user: str | None = None,
        osu_id: int | None = None,
        mode: app_commands.Choice[int] = None,
        detail: bool = False,
    ) -> None:
        await interaction.response.defer()
        user_id_for_l10n = interaction.user.id

        user_identifier = None
        identifier_type_for_api = "auto"

        if osu_id is not None and osu_user is not None:
            await interaction.followup.send(
                lstr(user_id_for_l10n, "error_only_one_identifier"), ephemeral=True
            )
            return
        if osu_id is not None:
            user_identifier = str(osu_id)
            identifier_type_for_api = "id"
            logger.debug(f"Profile lookup: osu_id='{user_identifier}', type='id'")
        elif osu_user:
            user_identifier = osu_user.strip()
            identifier_type_for_api = "username"
            logger.debug(
                f"Profile lookup: osu_user='{user_identifier}', type='username'"
            )
        else:
            bound_osu_id_val = await user_data_manager.get_user_binding(
                interaction.user.id
            )
            if bound_osu_id_val:
                user_identifier = str(bound_osu_id_val)
                identifier_type_for_api = "id"
                logger.debug(
                    f"Profile lookup: bound_user_id='{user_identifier}', type='id'"
                )
            else:
                await interaction.followup.send(
                    lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound")
                )
                return

        actual_mode_int = (
            mode.value if mode and hasattr(mode, "value") else config.DEFAULT_OSU_MODE
        )
        api_mode_for_get_user = (
            OSU_MODES_INT_TO_STRING.get(actual_mode_int) if mode is not None else None
        )
        logger.debug(
            f"Profile lookup: actual_mode_int='{actual_mode_int}', api_mode_for_get_user='{api_mode_for_get_user}'"
        )

        player_data = await self.osu_api.get_user(
            user_identifier=user_identifier,
            mode=api_mode_for_get_user,
            identifier_type=identifier_type_for_api,
        )

        if not player_data:
            if identifier_type_for_api == "id":
                error_message_key = "error_osu_user_id_not_found"
                await interaction.followup.send(
                    self._get_lstr_with_na_fallback(
                        user_id_for_l10n, error_message_key, user_identifier
                    )
                )
            else:  # username or auto that resolved to username
                error_message_key = "error_osu_user_not_found"
                await interaction.followup.send(
                    self._get_lstr_with_na_fallback(
                        user_id_for_l10n, error_message_key, user_identifier
                    )
                )
            return

        if mode is None and player_data.get("playmode"):
            returned_mode_str_from_api = player_data.get("playmode")
            REVERSE_OSU_MODES_INT_TO_STRING = {
                v: k for k, v in OSU_MODES_INT_TO_STRING.items()
            }
            if returned_mode_str_from_api in REVERSE_OSU_MODES_INT_TO_STRING:
                overridden_mode_int = REVERSE_OSU_MODES_INT_TO_STRING[
                    returned_mode_str_from_api
                ]
                if overridden_mode_int != actual_mode_int:
                    logger.debug(
                        f"Mode override: User didn't specify mode. API playmode='{returned_mode_str_from_api}'. Overriding actual_mode_int from {actual_mode_int} to {overridden_mode_int}."
                    )
                    actual_mode_int = overridden_mode_int
            else:
                logger.warning(
                    f"API returned unrecognized playmode: '{returned_mode_str_from_api}'. Sticking with default/initial mode: {actual_mode_int}"
                )

        self.get_mode_name(
            actual_mode_int, user_id_for_l10n
        )
        player_data.get("username") or self.get_na_value(user_id_for_l10n)
        user_id_from_api = player_data.get("id")

        mode_stats = player_data.get("statistics")
        pp_raw = mode_stats.get("pp") if mode_stats else None
        pp_rank = mode_stats.get("global_rank") if mode_stats else None
        pp_country_rank = mode_stats.get("country_rank") if mode_stats else None

        playcount = None
        if mode_stats and mode_stats.get("play_count") is not None:
            playcount = mode_stats.get("play_count")
        elif (
            player_data.get("play_count") is not None
        ):  # Fallback for older API or different structure
            playcount = player_data.get("play_count")

        level_current = (
            mode_stats.get("level", {}).get("current") if mode_stats else None
        )
        level_progress = (
            mode_stats.get("level", {}).get("progress", 0.0) if mode_stats else 0.0
        )
        level_display = (
            f"{level_current}.{int(level_progress):02d}"
            if level_current is not None
            else self.get_na_value(user_id_for_l10n)
        )

        accuracy = mode_stats.get("hit_accuracy") if mode_stats else None
        join_date_str = player_data.get("join_date")
        country_code = player_data.get("country_code", "")
        player_avatar_url = player_data.get("avatar_url")
        country_flag = get_country_flag_emoji(country_code)
        actual_player_username = player_data.get("username", "N/A")

        embed_title = ""
        if actual_player_username and actual_player_username != "N/A":
            english_title_format = f"{actual_player_username}'s OSU! Profile"
            template_key = "user_profile_title"
            localized_template = lstr(
                user_id_for_l10n, template_key, english_title_format
            )
            if (
                localized_template != english_title_format
                and "{}" in localized_template
                and "LSTR_KEY_ERROR" not in localized_template
                and "<translation_missing" not in localized_template
            ):
                try:
                    embed_title = localized_template.format(actual_player_username)
                except Exception as e:
                    logger.error(
                        f"Formatting localized title ('{localized_template}') failed: {e}. Using English fallback."
                    )
                    embed_title = english_title_format
            else:
                embed_title = english_title_format
        else:
            embed_title = lstr(
                user_id_for_l10n, "user_profile_title_na", "OSU! Profile"
            )

        embed_url = (
            f"https://osu.ppy.sh/users/{user_id_from_api}" if user_id_from_api else None
        )
        group_colour_hex = player_data.get("profile_colour")

        if not group_colour_hex and player_data.get("is_supporter", False):
            group_colour_hex = "#e6baff"  # Supporter pink/purple

        final_embed_color = discord.Color.blue()  # Default color
        if group_colour_hex:
            try:
                final_embed_color = discord.Color.from_str(group_colour_hex)
            except ValueError:
                logger.warning(
                    f"Could not parse color string: '{group_colour_hex}'. Falling back to default blue."
                )

        cover_url = player_data.get("cover_url")
        embed = discord.Embed(title=embed_title, color=final_embed_color, url=embed_url)
        if player_avatar_url:
            embed.set_thumbnail(url=str(player_avatar_url))

        if detail:
            combined_graph_buf = None
            has_rank_data_for_graph = False

            rank_history_from_player_data = player_data.get("rank_history")
            # playcount_history is no longer used for graph

            logger.debug(
                f"Raw rank_history for graph decision: {'Exists and has data' if rank_history_from_player_data and rank_history_from_player_data.get('data') else 'Missing or no data'}"
            )

            rank_has_data = (
                rank_history_from_player_data
                and rank_history_from_player_data.get("data")
            )

            if rank_has_data:  # Only rank graph is generated now
                try:
                    combined_graph_buf, generated_rank = (
                        self._generate_profile_combined_graph(
                            rank_history_from_player_data, user_id_for_l10n
                        )
                    )
                    has_rank_data_for_graph = generated_rank
                except Exception as e:
                    logger.error(
                        f"Error during profile graph generation call: {e}",
                        exc_info=True,
                    )

            detail_text = self._build_profile_detail_section(
                player_data,
                mode_stats,
                user_id_for_l10n,
                actual_mode_int,
                has_rank_graph=has_rank_data_for_graph,
            )
            embed.description = detail_text

            files_to_send = []
            if combined_graph_buf:
                graph_file = discord.File(
                    combined_graph_buf, filename="profile_graph.png"
                )
                embed.set_image(url="attachment://profile_graph.png")
                files_to_send.append(graph_file)

            if files_to_send:  # If there are files to send
                await interaction.followup.send(embed=embed, files=files_to_send)
            else:  # Otherwise, don't include the files parameter
                await interaction.followup.send(embed=embed)
            return
        # Not detail view (standard profile) - CORRECTED INDENTATION STARTS HERE
        if cover_url:
            embed.set_image(url=cover_url)

        pp_display = (
            f"{pp_raw:,.2f}pp"
            if pp_raw is not None
            else self.get_na_value(user_id_for_l10n)
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(user_id_for_l10n, "user_profile_pp"),
            value=pp_display,
            inline=True,
        )

        accuracy_display = (
            f"{accuracy:,.2f}%"
            if accuracy is not None
            else self.get_na_value(user_id_for_l10n)
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_accuracy"
            ),
            value=accuracy_display,
            inline=True,
        )

        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_level"
            ),
            value=level_display,
            inline=True,
        )

        global_rank_display = (
            f"#{pp_rank:,}"
            if pp_rank is not None
            else self.get_na_value(user_id_for_l10n)
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_global_rank"
            ),
            value=global_rank_display,
            inline=True,
        )

        country_rank_display = (
            f"{country_flag} #{pp_country_rank:,}"
            if pp_country_rank is not None
            else self.get_na_value(user_id_for_l10n)
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_country_rank"
            ),
            value=country_rank_display,
            inline=True,
        )

        playcount_display = (
            f"{playcount:,}"
            if playcount is not None
            else self.get_na_value(user_id_for_l10n)
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_play_count"
            ),
            value=playcount_display,
            inline=True,
        )

        join_date_display = self.get_na_value(user_id_for_l10n)
        if join_date_str:
            try:
                join_dt = datetime.datetime.fromisoformat(
                    join_date_str
                )
                join_date_display = (
                    self.format_datetime_obj(join_dt, user_id_for_l10n)
                    + f" ({self.time_since(join_dt, user_id_for_l10n)})"
                )
            except ValueError:
                logger.warning(f"Could not parse join_date_str: {join_date_str}")
                join_date_display = join_date_str
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_join_date"
            ),
            value=join_date_display,
            inline=False,
        )

        mode_emoji = MODE_EMOJI_STRINGS.get(actual_mode_int, "")
        mode_display_name = self.get_mode_name(actual_mode_int, user_id_for_l10n)
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "user_profile_game_mode"
            ),
            value=f"{mode_emoji} {mode_display_name}".strip(),
            inline=False,
        )

        await interaction.followup.send(embed=embed)
        # No return here, end of standard profile flow

    def _generate_profile_combined_graph(self, rank_history_full, user_id_for_l10n):
        rank_data = rank_history_full.get("data") if rank_history_full else None
        has_rank_data = bool(rank_data)  # True if rank_data is not None and not empty

        if not has_rank_data:  # This handles empty list or None
            logger.info("No rank history data available to generate graph.")
            return None, False  # Return buf, has_rank_data

        # NEW CHECK: If 0 is in rank_data (and rank_data is not empty, checked by has_rank_data),
        # treat it as N/A and don't generate graph.
        # A rank of 0 is generally not a valid rank in osu! (ranks are usually >= 1).
        if 0 in rank_data:
            logger.info(
                "Rank history data contains 0, which is treated as N/A. Graph will not be generated."
            )
            return None, False

        get_user_language(str(user_id_for_l10n))
        plt.style.use("seaborn-v0_8-darkgrid")

        fig, ax_rank = plt.subplots(1, 1, figsize=(7, 4), dpi=120)

        fig.patch.set_facecolor("#23272A")

        title_rank = lstr(
            user_id_for_l10n, "graph_title_rank_history", "Rank History (90 days)"
        )
        logger.debug(f"Graph title_rank for legend: '{title_rank}'")

        ax_rank.plot(
            list(range(1, len(rank_data) + 1)), rank_data, color="#bfaaff", linewidth=2
        )
        ax_rank.set_title(title_rank, fontsize=12, color="white", pad=10)
        ax_rank.set_ylabel(
            lstr(user_id_for_l10n, "graph_ylabel_rank", "Rank"), color="white"
        )
        ax_rank.invert_yaxis()
        ax_rank.tick_params(axis="x", colors="white")
        ax_rank.tick_params(axis="y", colors="white")

        ax_rank.grid(alpha=0.3)
        ax_rank.set_xlabel(
            lstr(user_id_for_l10n, "graph_xlabel_days", "Days (Most Recent)"),
            color="white",
        )

        ax_rank.set_facecolor("#23272A")
        for spine in ax_rank.spines.values():
            spine.set_color("#99aab5")

        plt.tight_layout(pad=2.0)
        buf = io.BytesIO()
        plt.savefig(
            buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        buf.seek(0)
        plt.close(fig)
        logger.info(
            f"Successfully generated profile rank graph. Has rank data: {has_rank_data}"
        )
        return buf, has_rank_data

    @app_commands.command(
        name="mapper", description="Shows osu! mapping statistics for a user."
    )
    @app_commands.describe(
        osu_user="osu! username (optional)", osu_id="osu! user ID (optional)"
    )
    async def mapper(
        self, interaction: discord.Interaction, osu_user: str | None = None, osu_id: int | None = None
    ) -> None:
        await interaction.response.defer()
        user_id_for_l10n = interaction.user.id
        # 僅能輸入一個參數
        if osu_user and osu_id is not None:
            await interaction.followup.send(
                lstr(user_id_for_l10n, "error_only_one_identifier"), ephemeral=True
            )
            return
        user_identifier = None
        identifier_type = None
        if osu_id is not None:
            user_identifier = str(osu_id)
        elif osu_user:
            user_identifier = osu_user.strip()
            if user_identifier.isdigit():
                identifier_type = "username"
        else:
            bound_osu_user = await user_data_manager.get_user_binding(
                interaction.user.id
            )
            if bound_osu_user:
                user_identifier = str(bound_osu_user)
            else:
                await interaction.followup.send(
                    lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound")
                )
                return
        if identifier_type == "username":
            player_data = await self.osu_api.get_user(
                user_identifier=user_identifier, identifier_type=identifier_type
            )
        else:
            player_data = await self.osu_api.get_user(user_identifier=user_identifier)
        if not player_data:
            error_message = self._get_lstr_with_na_fallback(
                user_id_for_l10n, "error_user_not_found", user_identifier
            )
            await interaction.followup.send(error_message)
            return

        actual_user_id = player_data.get("id")
        actual_username = player_data.get("username", user_identifier)
        player_avatar_url = player_data.get("avatar_url")
        country_code = player_data.get("country_code")
        get_country_flag_emoji(country_code) if country_code else ""

        logger.debug(
            f"[USER_COG /mapper] Fetched user: ID {actual_user_id}, Username: {actual_username}"
        )

        beatmap_types_to_fetch = [
            "ranked",
            "loved",
            "graveyard",
            "pending",
            "nominated",
        ]
        all_beatmapsets = {}

        logger.debug(
            f"[USER_COG /mapper] Starting to fetch beatmapsets for user {actual_user_id}"
        )
        for bs_type in beatmap_types_to_fetch:
            logger.debug(f"[USER_COG /mapper] Fetching type: {bs_type}")
            offset = 0
            limit = 50
            # Max 20 pages * 50 items/page = 1000 items per type.
            # Adjust max_fetches_per_type if more are needed, but be mindful of API rate limits and command execution time.
            max_fetches_for_type = 1000
            current_fetches_for_type = 0

            while current_fetches_for_type < max_fetches_for_type:
                logger.debug(
                    f"[USER_COG /mapper] Fetching {bs_type} - offset: {offset}, current_fetches_for_type: {current_fetches_for_type}"
                )
                beatmapsets_page = await self.osu_api.get_user_beatmapsets(
                    user_id=actual_user_id,
                    beatmap_type=bs_type,
                    limit=limit,
                    offset=offset,
                )

                if beatmapsets_page is None:
                    logger.error(
                        f"[USER_COG /mapper] API error fetching {bs_type} beatmapsets for user {actual_user_id} at offset {offset}"
                    )
                    break

                if not beatmapsets_page:
                    logger.debug(
                        f"[USER_COG /mapper] No more {bs_type} beatmapsets found at offset {offset}."
                    )
                    break

                for bm_set in beatmapsets_page:
                    if bm_set and bm_set.get("id"):
                        all_beatmapsets[bm_set["id"]] = bm_set
                        current_fetches_for_type += 1

                if len(beatmapsets_page) < limit:
                    logger.debug(
                        f"[USER_COG /mapper] Reached last page for {bs_type} (received {len(beatmapsets_page)} items)."
                    )
                    break

                offset += len(beatmapsets_page)

                if current_fetches_for_type >= max_fetches_for_type:
                    logger.warning(
                        f"[USER_COG /mapper] Reached max_fetches_for_type ({max_fetches_for_type}) for type {bs_type}. Stopping."
                    )
                    break

        logger.debug(
            f"[USER_COG /mapper] Total unique beatmapsets fetched: {len(all_beatmapsets)}"
        )

        hosted_mapsets_list = list(all_beatmapsets.values())

        total_mapsets_hosted = len(hosted_mapsets_list)
        ranked_loved_sets_count = 0
        total_favourites = 0

        # Get additional stats from the player_data (user object)
        kudosu_total = player_data.get("kudosu", {}).get(
            "total"
        )  # Can be None if not present
        followers_count = player_data.get("follower_count")  # Can be None
        guest_diffs_count = player_data.get("guest_beatmapset_count")  # Can be None
        # also player_data.get('ranked_beatmapset_count') and player_data.get('loved_beatmapset_count') exist
        # but we are calculating ranked/loved from the fetched sets for more control.

        latest_submission_date_obj = None
        earliest_submission_date_obj = None
        latest_beatmapset_obj = None  # ADDED: To store the latest beatmapset object

        for bm_set in hosted_mapsets_list:
            status = bm_set.get("status")
            # In APIv2, 'approved' is a legacy status often represented as 'ranked'.
            # 'qualified' is also sometimes seen and might transition to ranked.
            # For simplicity, counting 'ranked' and 'loved'.
            if status in {"ranked", "loved", "qualified", "approved"}:
                ranked_loved_sets_count += 1

            total_favourites += bm_set.get("favourite_count", 0)

            # Prefer 'submitted_date' for "first seen" by system.
            # 'last_updated' could be more recent than 'ranked_date' or 'submitted_date'.
            # 'ranked_date' is specific to when it achieved ranked status.
            date_str_to_parse = bm_set.get("submitted_date")
            if not date_str_to_parse:  # Fallback if submitted_date is missing
                date_str_to_parse = bm_set.get("last_updated")

            if date_str_to_parse:
                try:
                    # API v2 dates are ISO 8601 with Z (UTC) e.g. "2023-01-15T10:30:00+00:00" or "2023-01-15T10:30:00Z"
                    current_bm_date = datetime.datetime.fromisoformat(
                        date_str_to_parse
                    )
                    if (
                        latest_submission_date_obj is None
                        or current_bm_date > latest_submission_date_obj
                    ):
                        latest_submission_date_obj = current_bm_date
                        latest_beatmapset_obj = bm_set  # UPDATED: Store the object
                    if (
                        earliest_submission_date_obj is None
                        or current_bm_date < earliest_submission_date_obj
                    ):
                        earliest_submission_date_obj = current_bm_date
                except ValueError:
                    logger.warning(
                        f"[USER_COG /mapper] Could not parse date: {date_str_to_parse}"
                    )

        mapping_duration_str = self._get_lstr_with_na_fallback(
            user_id_for_l10n, "value_not_available"
        )
        if earliest_submission_date_obj:
            mapping_duration_str = self.time_since(
                earliest_submission_date_obj, user_id_for_l10n, short=False
            )

        # Determine embed title for mapper stats
        english_template_str = "{}'s Mapping Stats"
        default_embed_title = english_template_str.format(actual_username)
        embed_title_to_use = default_embed_title
        localized_template_candidate = lstr(
            user_id_for_l10n, "mapper_stats_embed_title", "mapper_stats_embed_title"
        )

        if (
            localized_template_candidate != "mapper_stats_embed_title"
            and "{}" in localized_template_candidate
            and not any(
                err_indicator in localized_template_candidate
                for err_indicator in ["LSTR_KEY_ERROR", "<translation_missing"]
            )
        ):
            try:
                embed_title_to_use = localized_template_candidate.format(
                    actual_username
                )
            except Exception as e:
                logger.error(
                    f"[USER_COG /mapper] Formatting localized mapper title ('{localized_template_candidate}') failed: {e}. Falling back to English title."
                )

        author_name = embed_title_to_use
        author_profile_url = (
            f"https://osu.ppy.sh/users/{actual_user_id}" if actual_user_id else None
        )
        author_icon_display_url = str(player_avatar_url) if player_avatar_url else None

        # Create embed: No main title, author field will contain the main info.
        # Color is kept. Embed URL is removed as there's no main title.
        embed = discord.Embed(color=discord.Color.purple())

        # Set the author with the mapper's name, profile link, and avatar
        embed.set_author(
            name=author_name, url=author_profile_url, icon_url=author_icon_display_url
        )

        # Thumbnail is no longer needed as avatar is in author icon.
        # Old embed.url (to beatmapsets/extra) is also removed.
        # If this link is critical, it can be added back in a field or description.

        embed.add_field(
            name=self._get_lstr_with_na_fallback(user_id_for_l10n, "mapper_total_sets"),
            value=str(total_mapsets_hosted),
            inline=True,
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "mapper_ranked_loved"
            ),
            value=str(ranked_loved_sets_count),
            inline=True,
        )
        guest_diffs_display = (
            str(guest_diffs_count)
            if guest_diffs_count is not None
            else self._get_lstr_with_na_fallback(
                user_id_for_l10n, "value_not_available"
            )
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "mapper_guest_difficulties"
            ),
            value=guest_diffs_display,
            inline=True,
        )

        first_upload_display = (
            self.format_datetime_obj(earliest_submission_date_obj, user_id_for_l10n)
            if earliest_submission_date_obj
            else self._get_lstr_with_na_fallback(user_id_for_l10n, "never_uploaded")
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "mapper_first_upload"
            ),
            value=first_upload_display,
            inline=True,
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "mapper_mapping_duration"
            ),
            value=mapping_duration_str,
            inline=True,
        )

        embed.add_field(
            name=self._get_lstr_with_na_fallback(
                user_id_for_l10n, "mapper_total_favourites"
            ),
            value=f"{total_favourites:,}",
            inline=True,
        )

        followers_display = (
            f"{followers_count:,}"
            if followers_count is not None
            else self._get_lstr_with_na_fallback(
                user_id_for_l10n, "value_not_available"
            )
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(user_id_for_l10n, "mapper_followers"),
            value=followers_display,
            inline=True,
        )

        # Add a blank inline field to push Kudosu to the third column
        embed.add_field(
            name="\u200b", value="\u200b", inline=True
        )  # Invisible characters for a blank field

        kudosu_display = (
            f"{kudosu_total:,}"
            if kudosu_total is not None
            else self._get_lstr_with_na_fallback(
                user_id_for_l10n, "value_not_available"
            )
        )
        embed.add_field(
            name=self._get_lstr_with_na_fallback(user_id_for_l10n, "mapper_kudosu"),
            value=kudosu_display,
            inline=True,
        )

        # Add a blank non-inline field for spacing before Latest Submission
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # --- MODIFIED SECTION for Latest Submission (Moved to bottom, corrected newline) ---
        if latest_beatmapset_obj:
            lb_title = latest_beatmapset_obj.get("title", "Unknown Title")
            lb_artist = latest_beatmapset_obj.get("artist", "Unknown Artist")
            lb_id = latest_beatmapset_obj.get("id")
            lb_url = f"https://osu.ppy.sh/beatmapsets/{lb_id}" if lb_id else None

            lb_cover_url = latest_beatmapset_obj.get("covers", {}).get("card")
            if not lb_cover_url:  # Fallback to 'cover' if 'card' is not available
                lb_cover_url = latest_beatmapset_obj.get("covers", {}).get("cover")

            latest_submission_display_value = ""
            if lb_url:
                latest_submission_display_value = f"[{lb_artist} - {lb_title}]({lb_url})\n"  # CORRECTED to single backslash
            else:
                latest_submission_display_value = (
                    f"{lb_artist} - {lb_title}\n"  # CORRECTED to single backslash
                )

            if latest_submission_date_obj:
                latest_submission_display_value += self.format_datetime_obj(
                    latest_submission_date_obj, user_id_for_l10n
                )

            embed.add_field(
                name=self._get_lstr_with_na_fallback(
                    user_id_for_l10n, "mapper_latest_submission"
                ),
                value=latest_submission_display_value,
                inline=False,
            )
            if lb_cover_url:
                embed.set_image(url=lb_cover_url)
        else:  # Case where user has no submissions at all
            latest_upload_display = self._get_lstr_with_na_fallback(
                user_id_for_l10n, "never_uploaded"
            )
            embed.add_field(
                name=self._get_lstr_with_na_fallback(
                    user_id_for_l10n, "mapper_latest_submission"
                ),  # Use the same key for consistency
                value=latest_upload_display,
                inline=False,
            )
        # --- END MODIFIED SECTION ---

        footer_text_parts = []
        # Simplified footer to only show User ID to avoid issues with country flag display
        footer_text_parts.append(f"ID: {actual_user_id}")

        embed.set_footer(text=" | ".join(filter(None, footer_text_parts)))

        logger.debug(f"[USER_COG /mapper] Sending embed for {actual_username}")
        await interaction.followup.send(embed=embed)
        logger.debug(f"[USER_COG /mapper] Mapper embed sent for {actual_username}")

    @app_commands.command(
        name="setuser", description="Bind your Discord account to your osu! account."
    )
    @app_commands.describe(
        osu_user="Your osu! username (optional)", osu_id="Your osu! user ID (optional)"
    )
    async def setuser(
        self, interaction: discord.Interaction, osu_user: str | None = None, osu_id: int | None = None
    ) -> None:
        user_id_for_l10n = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)

        if osu_user and osu_id:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "error_only_one_identifier",
                    "Please provide only one of osu! username or ID, not both.",
                )
            )
            return

        identifier_to_use = None
        identifier_type = None

        if osu_id:
            identifier_to_use = str(osu_id)
            identifier_type = "id"
        elif osu_user:
            identifier_to_use = osu_user
            identifier_type = "username"

        if not identifier_to_use:
            # Check if user has an existing binding to display
            existing_binding = await user_data_manager.get_user_binding(
                interaction.user.id
            )
            if existing_binding:
                # Attempt to get the osu! user object to display the current official username
                try:
                    bound_player_data = await self.osu_api.get_user(
                        user_identifier=existing_binding
                    )  # get_user should handle if existing_binding is ID or username based on its content if type not specified
                    if bound_player_data and bound_player_data.get("username"):
                        await interaction.followup.send(
                            lstr(
                                user_id_for_l10n,
                                "info_your_bound_account",
                                "Your currently bound osu! account is: {0}",
                                bound_player_data.get("username"),
                            )
                        )
                    else:
                        # Fallback if we can't fetch the username, just show what's stored
                        await interaction.followup.send(
                            lstr(
                                user_id_for_l10n,
                                "info_your_bound_account",
                                "Your currently bound osu! account is: {0}",
                                existing_binding,
                            )
                        )
                except Exception as e:
                    logger.error(
                        f"Error fetching details for existing binding {existing_binding} for user {interaction.user.id}: {e}"
                    )
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "info_your_bound_account",
                            "Your currently bound osu! account is: {0}",
                            existing_binding,
                        )
                        + " (Could not verify current username)"
                    )
            else:
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n,
                        "info_no_bound_account",
                        "You have not bound any osu! account yet. Use `/setuser <your osu! username or ID>` to bind.",
                    )
                )
            return

        # Attempt to get the user from osu! API to confirm validity and get official username
        try:
            player_data = await self.osu_api.get_user(
                user_identifier=identifier_to_use, identifier_type=identifier_type
            )
            if not player_data or not player_data.get("id"):
                # Construct appropriate error message based on type
                if identifier_type == "id":
                    error_key = "error_osu_user_id_not_found"
                    error_default = "osu! player id {} not found."
                else:  # username
                    error_key = "error_osu_user_not_found"
                    error_default = "osu! player {} not found."
                await interaction.followup.send(
                    lstr(user_id_for_l10n, error_key, error_default, identifier_to_use)
                )
                return

            official_osu_username = player_data.get("username")
            osu_id_to_store = str(
                player_data.get("id")
            )  # Store ID for consistency if possible, or username if ID fetch fails

            # Use osu_id_to_store for binding as it's more reliable, but display official_osu_username
            await user_data_manager.set_user_binding(
                interaction.user.id, osu_id_to_store
            )
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "info_setuser_success",
                    "Successfully bound osu! account {0}.",
                    official_osu_username,
                )
            )

        except Exception as e:
            logger.error(
                f"Error during /setuser for {identifier_to_use} (user: {interaction.user.id}): {e}"
            )
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "error_generic_command",
                    "An unexpected error occurred while executing the command: {}",
                    str(e),
                )
            )

    @app_commands.command(
        name="unsetuser",
        description="Unbind your Discord account from your osu! account.",
    )
    async def unsetuser(self, interaction: discord.Interaction) -> None:
        user_id_for_l10n = str(interaction.user.id)
        discord_user_id = interaction.user.id
        await interaction.response.defer(ephemeral=True)

        removed = await user_data_manager.remove_user_binding(discord_user_id)

        if removed:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "info_unsetuser_success",
                    "Successfully unbound your osu! account.",
                )
            )
        else:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "error_unsetuser_not_bound",
                    "You do not have an osu! account bound to your Discord account.",
                )
            )


async def setup(bot: commands.Bot) -> None:
    # Similar to OsuCog, mode choices for /profile can be added here if desired,
    # but the current approach of `mode: app_commands.Choice[int] = None` works simply.
    await bot.add_cog(UserCog(bot))
    logger.info("UserCog loaded.")
