import discord
from discord import app_commands
from discord.ext import commands
import datetime
from private import config  # For DEFAULT_OSU_MODE
from utils.osu_api import OsuAPI
from utils.localization import (
    get_localized_string as lstr,
    get_user_language,
    _translations,
)
import re

# import traceback # No longer needed
from utils import user_data_manager
from .user_cog import MODE_EMOJI_STRINGS, MODE_FALLBACK_TEXT  # Import from user_cog
from cogs.pp_cog import format_mods_for_display  # CORRECTED IMPORT
from utils.beatmap_utils import get_beatmap_status_display  # IMPORT THE NEW FUNCTION
# from utils.image_utils import create_score_card # For image generation # REMOVED

from loguru import logger

# osu! 遊戲模式的映射，用於顯示 和 API v2 的模式字串
OSU_MODES_INT_TO_STRING = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}
# 用於本地化顯示的鍵名保持不變
OSU_MODES_L10N_KEYS = {0: "mode_std", 1: "mode_taiko", 2: "mode_ctb", 3: "mode_mania"}

# 新增：僅包含模式名稱的本地化鍵
OSU_MODES_NAME_ONLY_L10N_KEYS = {
    0: "mode_name_only_std",
    1: "mode_name_only_taiko",
    2: "mode_name_only_ctb",
    3: "mode_name_only_mania",
}

# MODE_EMOJI_STRINGS and MODE_FALLBACK_TEXT are now imported from user_cog

# 評價的顏色映射
RANK_COLORS = {
    "XH": 0xAAAAFF,  # SS Silver
    "X": 0xFFD700,  # SS Gold
    "SH": 0xC0C0C0,  # S Silver
    "S": 0xFFE4B5,  # S Gold
    "A": 0x7FFF00,  # A Green
    "B": 0xFFC0CB,  # B Pink
    "C": 0xFF0000,  # C Red
    "D": 0x808080,  # D Grey
    "F": 0x000000,  # Fail Black
}

# New Rank Emoji Map
RANK_EMOJI_MAP = {
    "XH": "<:rkhdfl:1373246417350561844>",  # Placeholder for SS HD/FL, actual logic below
    "X": "<:rkss:1373246926379679836>",
    "SH": "<:rkhdfl:1373246417350561844>",  # Placeholder for S HD/FL, actual logic below
    "S": "<:rks:1373246734079230072>",
    "A": "<:rka:1373246979211132988>",
    "B": "<:rkb:1373247010169159721>",
    "C": "<:rkc:1373247035268006010>",
    "D": "<:rkd:1373247061360644187>",
}


# NEW VIEW FOR /best COMMAND
class PreviousBestButton(discord.ui.Button):
    def __init__(
        self,
        user_id_for_l10n: int,
        style=discord.ButtonStyle.secondary,
        emoji="⬅️",
        **kwargs,
    ):
        super().__init__(
            label=lstr(user_id_for_l10n, "button_previous_bp", "Previous BP"),
            style=style,
            emoji=emoji,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        view: BestScoreView = self.view
        if view is None or view.current_index == 0:
            await interaction.response.defer()  # Should be disabled, but good practice
            return

        view.current_index -= 1
        await view.update_embed(interaction)


class NextBestButton(discord.ui.Button):
    def __init__(
        self,
        user_id_for_l10n: int,
        style=discord.ButtonStyle.secondary,
        emoji="➡️",
        **kwargs,
    ):
        super().__init__(
            label=lstr(user_id_for_l10n, "button_next_bp", "Next BP"),
            style=style,
            emoji=emoji,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        view: BestScoreView = self.view
        if view is None or view.current_index >= len(view.scores_list) - 1:
            await interaction.response.defer()  # Should be disabled
            return

        view.current_index += 1
        await view.update_embed(interaction)


# New Modal for Jump to BP
class JumpToBPModal(discord.ui.Modal):
    def __init__(self, view: "BestScoreView", user_id_for_l10n: int):
        super().__init__(
            title=lstr(
                user_id_for_l10n, "modal_jump_to_bp_title", "Jump to Specific BP"
            )
        )
        self.parent_view = view
        self.user_id_for_l10n = user_id_for_l10n

        self.bp_rank_input = discord.ui.TextInput(
            label=lstr(
                user_id_for_l10n,
                "modal_bp_rank_label",
                "BP Rank (1-{max_bp})",  # English fallback
                max_bp=len(self.parent_view.scores_list)
                if self.parent_view.scores_list
                else 200,
            ),
            placeholder=lstr(
                user_id_for_l10n, "modal_bp_rank_placeholder", "Enter a number"
            ),
            min_length=1,
            max_length=3,  # Max 100 for BP usually
        )
        self.add_item(self.bp_rank_input)

    async def on_submit(self, interaction: discord.Interaction):
        input_value = self.bp_rank_input.value
        try:
            rank_to_jump = int(input_value)
            if not (1 <= rank_to_jump <= len(self.parent_view.scores_list)):
                await interaction.response.send_message(
                    lstr(
                        self.user_id_for_l10n,
                        "error_invalid_bp_rank_range",
                        "輸入的BP排名無效或超出範圍。",
                    ),
                    ephemeral=True,
                )
                return

            self.parent_view.current_index = (
                rank_to_jump - 1
            )  # Convert to 0-based index
            await self.parent_view.update_embed(
                interaction
            )  # This will defer internally and edit
        except ValueError:
            await interaction.response.send_message(
                lstr(
                    self.user_id_for_l10n,
                    "error_invalid_bp_rank_format",
                    "請輸入有效的數字BP排名。",
                ),
                ephemeral=True,
            )
        except Exception as e:  # Catch other potential errors from update_embed
            logger.error(f"[JumpToBPModal on_submit] Error: {e}", exc_info=True)
            await interaction.response.send_message(
                lstr(self.user_id_for_l10n, "error_generic", "處理跳轉時發生錯誤。"),
                ephemeral=True,
            )


class JumpToBPButton(discord.ui.Button):
    def __init__(
        self,
        user_id_for_l10n: int,
        style=discord.ButtonStyle.secondary,
        emoji="\u23f9",
        **kwargs,
    ):  # Unicode for :stop_button:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_jump_to_bp", "Jump"),
            style=style,
            emoji=emoji,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        view: BestScoreView = self.view
        if view is None or not view.scores_list:
            await interaction.response.defer()  # Should be disabled if no scores
            return
        # Pass user_id_for_l10n from the view to the modal for its internal l10n
        modal = JumpToBPModal(view=view, user_id_for_l10n=view.user_id_for_l10n)
        await interaction.response.send_modal(modal)


class BestScoreView(discord.ui.View):
    def __init__(
        self,
        cog_instance,
        scores: list,
        osu_player_name: str,
        player_avatar_url: str,
        mode_int: int,
        user_id_for_l10n: int,
        timeout=300,
    ):  # Timeout in seconds
        super().__init__(timeout=timeout)
        self.cog = cog_instance  # OsuCog instance
        self.scores_list = scores
        logger.debug(
            f"[BestScoreView __init__] Initialized with {len(self.scores_list)} scores for player {osu_player_name}."
        )  # Log count in View
        self.osu_player_name = osu_player_name
        self.player_avatar_url = player_avatar_url
        self.mode_int = mode_int
        self.user_id_for_l10n = user_id_for_l10n
        self.current_index = 0

        self.prev_button = PreviousBestButton(user_id_for_l10n=self.user_id_for_l10n)
        self.next_button = NextBestButton(user_id_for_l10n=self.user_id_for_l10n)
        self.jump_button = JumpToBPButton(user_id_for_l10n=self.user_id_for_l10n)

        self.add_item(self.prev_button)
        self.add_item(self.jump_button)  # Moved to middle position
        self.add_item(self.next_button)

        self._update_button_states()

    def _update_button_states(self):
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.scores_list) - 1
        self.jump_button.disabled = not self.scores_list  # Disable if no scores
        # Update button labels with current user's language if interaction is available
        # For now, labels are set at init. If dynamic l10n for buttons is needed, it's more complex.

    async def update_embed(self, interaction: discord.Interaction):
        await (
            interaction.response.defer()
        )  # Defer response as embed generation might take time

        current_score = self.scores_list[self.current_index]
        # We need to call the cog's embed creation method.
        # Assuming _create_score_embed exists or will be created in OsuCog
        new_embed = await self.cog._create_score_embed(
            score_data=current_score,
            player_name=self.osu_player_name,
            player_avatar_url=self.player_avatar_url,
            mode_int=self.mode_int,
            user_id_for_l10n=self.user_id_for_l10n,
            rank_in_top=self.current_index + 1,  # Pass the 1-based rank
        )

        self._update_button_states()
        await interaction.edit_original_response(embed=new_embed, view=self)

    async def on_timeout(self):
        # Optionally disable buttons on timeout
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        # Check if message exists before editing
        if hasattr(self, "message") and self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # Message might have been deleted


# NEW VIEW FOR /recent COMMAND
class PreviousRecentButton(discord.ui.Button):
    def __init__(
        self,
        user_id_for_l10n: int,
        style=discord.ButtonStyle.secondary,
        emoji="⬅️",
        **kwargs,
    ):
        super().__init__(
            label=lstr(user_id_for_l10n, "button_previous_recent", "Previous Play"),
            style=style,
            emoji=emoji,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        view: RecentScoreView = self.view
        if view is None or view.current_index == 0:
            await interaction.response.defer()
            return
        view.current_index -= 1
        await view.update_embed(interaction)


class NextRecentButton(discord.ui.Button):
    def __init__(
        self,
        user_id_for_l10n: int,
        style=discord.ButtonStyle.secondary,
        emoji="➡️",
        **kwargs,
    ):
        super().__init__(
            label=lstr(user_id_for_l10n, "button_next_recent", "Next Play"),
            style=style,
            emoji=emoji,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        view: RecentScoreView = self.view
        if view is None or view.current_index >= len(view.scores_list) - 1:
            await interaction.response.defer()
            return
        view.current_index += 1
        await view.update_embed(interaction)


class RecentScoreView(discord.ui.View):
    def __init__(
        self,
        cog_instance,
        scores: list,
        osu_player_name: str,
        player_avatar_url: str,
        mode_int: int,
        user_id_for_l10n: int,
        timeout=300,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog_instance
        self.scores_list = scores
        self.osu_player_name = osu_player_name
        self.player_avatar_url = player_avatar_url
        self.mode_int = mode_int
        self.user_id_for_l10n = user_id_for_l10n
        self.current_index = 0

        self.prev_button = PreviousRecentButton(user_id_for_l10n=self.user_id_for_l10n)
        self.next_button = NextRecentButton(user_id_for_l10n=self.user_id_for_l10n)

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        self._update_button_states()

    def _update_button_states(self):
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.scores_list) - 1

    async def update_embed(self, interaction: discord.Interaction):
        await interaction.response.defer()
        current_score = self.scores_list[self.current_index]
        # Use the same _create_score_embed, rank_in_top will be None for recent plays
        new_embed = await self.cog._create_score_embed(
            score_data=current_score,
            player_name=self.osu_player_name,
            player_avatar_url=self.player_avatar_url,
            mode_int=self.mode_int,
            user_id_for_l10n=self.user_id_for_l10n,
        )
        self._update_button_states()
        await interaction.edit_original_response(embed=new_embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if hasattr(self, "message") and self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


class OsuCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client

    def _get_beatmap_attributes_display(
        self, beatmap_compact: dict, mode_int: int, user_id_for_l10n: int
    ) -> tuple[str, str] | None:
        cs = beatmap_compact.get("cs", 0.0)
        ar = beatmap_compact.get("ar")
        od = beatmap_compact.get("accuracy", 0.0)  # 'accuracy' in API v2 is OD
        hp = beatmap_compact.get("drain", 0.0)  # 'drain' in API v2 is HP

        mode_name_for_field = self.get_mode_name(mode_int, user_id_for_l10n)

        attributes = []
        if mode_int == 0:  # osu!standard
            attributes.append(f"CS: {cs:.1f}")
            if ar is not None:
                attributes.append(f"AR: {ar:.1f}")
            attributes.append(f"OD: {od:.1f}")
            attributes.append(f"HP: {hp:.1f}")
        elif mode_int == 1:  # Taiko
            attributes.append(f"OD: {od:.1f}")
            attributes.append(f"HP: {hp:.1f}")
        elif mode_int == 2:  # Catch
            attributes.append(f"CS: {cs:.1f}")
            if ar is not None:
                attributes.append(f"AR: {ar:.1f}")
            attributes.append(f"HP: {hp:.1f}")
        elif mode_int == 3:  # Mania
            attributes.append(f"OD: {od:.1f}")
            attributes.append(f"HP: {hp:.1f}")

        field_name_key = "beatmap_attributes_label"
        field_value_parts = [mode_name_for_field]
        if attributes:
            field_value_parts.append(" | ".join(attributes))
        else:  # Should not happen if mode_name_for_field is always present
            field_name_key = (
                "beatmap_mode_label"  # Fallback to just mode label if no attributes
            )

        final_field_name = self._get_lstr_with_na_fallback(
            user_id_for_l10n, field_name_key
        )
        final_field_value = "\n".join(
            field_value_parts
        )  # Use newline to separate mode name and stats string

        return (final_field_name, final_field_value)

    def get_na_value(self, user_id_for_l10n: int) -> str:
        # Determine language for N/A value
        current_lang = get_user_language(str(user_id_for_l10n))
        na_translation = _translations.get(current_lang, {}).get(
            "value_not_available", "N/A"
        )
        # No need for complex checks if we fetch directly and have a hardcoded fallback
        return na_translation

    def _get_lstr_with_na_fallback(self, user_id_for_l10n: int, key: str, *args) -> str:
        raw_translation = lstr(user_id_for_l10n, key, *args)
        if (
            "<translation_missing" in raw_translation
            or "<formatting_error" in raw_translation
        ):
            return self.get_na_value(user_id_for_l10n)
        return raw_translation

    def get_mode_name(
        self, mode_int: int, user_id_for_l10n: int, name_only: bool = False
    ) -> str:
        current_lang = get_user_language(str(user_id_for_l10n))
        logger.debug(
            f"[OSU_COG get_mode_name] Called with mode_int: {mode_int}, user_id: {user_id_for_l10n}, determined_lang: {current_lang}, name_only: {name_only}"
        )

        key_map = OSU_MODES_NAME_ONLY_L10N_KEYS if name_only else OSU_MODES_L10N_KEYS
        l10n_key = key_map.get(
            mode_int, "mode_name_only_unknown" if name_only else "mode_unknown"
        )

        # Directly use _translations with current_lang
        localized_name = _translations.get(current_lang, {}).get(l10n_key)

        if (
            not localized_name or localized_name == l10n_key
        ):  # If key not found in current_lang translations
            # Try fallback to default language for the key
            localized_name = _translations.get(config.DEFAULT_LANGUAGE, {}).get(
                l10n_key
            )

        if (
            not localized_name or localized_name == l10n_key
        ):  # If still not found, use MODE_FALLBACK_TEXT
            localized_name = MODE_FALLBACK_TEXT.get(
                mode_int, "Unknown Mode"
            )  # Fallback to English hardcoded text

        logger.debug(f"[OSU_COG get_mode_name] Result: {localized_name}")
        return localized_name

    async def _determine_game_mode(
        self, requested_mode_int: int | None, player_data: dict, command_name: str
    ) -> int:
        """Determines the actual game mode to use based on user input and player defaults."""
        if requested_mode_int is not None:
            logger.debug(
                f"[OSU_COG /{command_name}] User provided mode: {requested_mode_int}"
            )
            return requested_mode_int
        else:
            user_api_default_mode_str = player_data.get("playmode")
            if user_api_default_mode_str:
                REVERSE_OSU_MODES_INT_TO_STRING = {
                    v: k for k, v in OSU_MODES_INT_TO_STRING.items()
                }  # Stays local for now
                if user_api_default_mode_str in REVERSE_OSU_MODES_INT_TO_STRING:
                    determined_mode_int = REVERSE_OSU_MODES_INT_TO_STRING[
                        user_api_default_mode_str
                    ]
                    logger.debug(
                        f"[OSU_COG /{command_name}] Using user API default mode: {user_api_default_mode_str} -> {determined_mode_int}"
                    )
                    return determined_mode_int
                else:
                    logger.debug(
                        f"[OSU_COG /{command_name}] User API default mode '{user_api_default_mode_str}' not recognized, using config default: {config.DEFAULT_OSU_MODE}"
                    )
                    return config.DEFAULT_OSU_MODE
            else:
                logger.debug(
                    f"[OSU_COG /{command_name}] No user API default mode, using config default: {config.DEFAULT_OSU_MODE}"
                )
                return config.DEFAULT_OSU_MODE

    async def _get_user_data(self, user_identifier: str, user_id_for_l10n: int):
        logger.debug(
            f"[OSU_COG _get_user_data] Attempting to get user: {user_identifier}"
        )
        user_data = await self.osu_api.get_user(user_identifier=user_identifier)
        if not user_data:
            error_message = lstr(
                user_id_for_l10n, "error_user_not_found", user_identifier
            )
            logger.debug(
                f"[OSU_COG _get_user_data] User not found. Returning error: {error_message}"
            )
            return None, error_message
        logger.debug(f"[OSU_COG _get_user_data] User found. Returning data.")
        return user_data, None

    @app_commands.command(
        name="recent", description="Shows the most recent osu! score for a user."
    )
    @app_commands.describe(
        osu_user="osu! username (optional)",
        osu_id="osu! user ID (optional)",
        mode="Game mode. Defaults to user's or server's default.",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="STD", value=0),
            app_commands.Choice(name="Taiko", value=1),
            app_commands.Choice(name="CTB", value=2),
            app_commands.Choice(name="Mania", value=3),
        ]
    )
    async def recent(
        self,
        interaction: discord.Interaction,
        osu_user: str = None,
        osu_id: int = None,
        mode: int = None,
    ):
        try:
            await interaction.response.defer()
            logger.debug(
                f"[OSU_COG /recent] CMD_INVOKED: osu_user='{osu_user}', osu_id='{osu_id}', mode={mode}"
            )
            user_id_for_l10n = interaction.user.id
            # 優先用 osu_id 查詢
            user_identifier = None
            if osu_id is not None:
                user_identifier = str(osu_id)
            elif osu_user:
                user_identifier = osu_user.strip()
            else:
                bound_osu_user = await user_data_manager.get_user_binding(
                    user_id_for_l10n
                )
                if bound_osu_user:
                    user_identifier = str(bound_osu_user)
                else:
                    await interaction.followup.send(
                        lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound")
                    )
                    return
            player_data, error_msg = await self._get_user_data(
                user_identifier, user_id_for_l10n
            )
            if error_msg:
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n, "error_user_not_found", str(user_identifier)
                    ),
                    ephemeral=True,
                )
                return

            numeric_user_id = player_data.get("id")
            player_name_for_embed = (
                player_data.get("username") or str(user_identifier).strip()
            )
            player_avatar_url = player_data.get("avatar_url", None)

            actual_mode_int = await self._determine_game_mode(
                mode, player_data, "recent"
            )

            actual_mode_str = OSU_MODES_INT_TO_STRING.get(actual_mode_int)
            if actual_mode_str is None:
                logger.error(
                    f"[OSU_COG ERROR /recent] MODE_RESOLVE_FAILED: actual_mode_str is None for actual_mode_int={actual_mode_int}. This is a critical bug."
                )
                await interaction.followup.send(
                    f"Internal error: Invalid game mode resolved for code '{actual_mode_int}'. Please report this.",
                    ephemeral=True,
                )
                return
            logger.debug(
                f"[OSU_COG DEBUG /recent] MODE_RESOLVE_SUCCESS: actual_mode_str='{actual_mode_str}' for mode_int={actual_mode_int}"
            )

            processed_user_input = str(user_identifier).strip()
            if not processed_user_input:
                logger.warning(
                    f"[OSU_COG WARNING /recent] USER_INPUT_EMPTY: osu_user input '{user_identifier}' was empty after stripping."
                )
                await interaction.followup.send(
                    "osu! username or ID cannot be empty. Please provide a valid identifier.",
                    ephemeral=True,
                )
                return
            logger.debug(
                f"[OSU_COG DEBUG /recent] USER_INPUT_PROCESSED: '{processed_user_input}'"
            )

            logger.debug(
                f"[OSU_COG DEBUG /recent] GET_USER_DATA_START: Calling _get_user_data for '{processed_user_input}'"
            )

            logger.debug(
                f"[OSU_COG DEBUG /recent] Fetching recent plays for user ID: {numeric_user_id}, mode: {actual_mode_str}"
            )

            # Fetch multiple recent plays (e.g., 50)
            recent_scores = await self.osu_api.get_user_recent(
                user_id=str(numeric_user_id),
                mode=actual_mode_str,
                limit=50,  # Fetch more for pagination
                include_fails=True,  # Parameter for get_user_recent (boolean or string '1')
            )

            if not recent_scores:
                logger.debug(
                    f"[OSU_COG DEBUG /recent] No recent plays found for user ID: {numeric_user_id} in mode {actual_mode_str}."
                )
                error_message_key = "error_no_recent_plays"
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n, error_message_key, "", player_name_for_embed
                    ),
                    ephemeral=True,
                )
                return

            logger.debug(
                f"[OSU_COG DEBUG /recent] Fetched {len(recent_scores)} recent plays for user {player_name_for_embed} in mode {actual_mode_str}."
            )
            if recent_scores:
                logger.debug(
                    f"[OSU_COG DEBUG /recent] First score data (mode: {actual_mode_str}): {str(recent_scores[0])[:500]}..."
                )

            # Create initial embed for the first recent score
            initial_embed = await self._create_score_embed(
                score_data=recent_scores[0],
                player_name=player_name_for_embed,
                player_avatar_url=player_avatar_url,
                mode_int=actual_mode_int,
                user_id_for_l10n=user_id_for_l10n,
                # rank_in_top is not provided for recent plays
            )

            # Create the view
            view = RecentScoreView(
                cog_instance=self,
                scores=recent_scores,
                osu_player_name=player_name_for_embed,
                player_avatar_url=player_avatar_url,
                mode_int=actual_mode_int,
                user_id_for_l10n=user_id_for_l10n,
            )

            message = await interaction.followup.send(embed=initial_embed, view=view)
            view.message = message  # Store for on_timeout

        except Exception as e_fetch_recent:
            logger.error(
                f"[OSU_COG ERROR /recent] Error during fetching/accessing recent plays: {e_fetch_recent}",
                exc_info=True,
            )
            error_detail = (
                str(e_fetch_recent)
                if len(str(e_fetch_recent)) < 100
                else str(e_fetch_recent)[:100] + "..."
            )
            # Ensure fallback for lstr
            error_report_msg = lstr(
                user_id_for_l10n, "error_generic_command", error_detail
            )
            if "<translation_missing" in error_report_msg:
                error_report_msg = (
                    f"An error occurred while fetching recent play data: {error_detail}"
                )
            await interaction.followup.send(error_report_msg, ephemeral=True)

    @app_commands.command(name="best", description="Shows a user's top osu! score.")
    @app_commands.describe(
        osu_user="osu! username or ID",
        mode="Game mode. Defaults to user's or server's default.",
        bp_rank="BP rank to display (1-200, optional)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="STD", value=0),
            app_commands.Choice(name="Taiko", value=1),
            app_commands.Choice(name="CTB", value=2),
            app_commands.Choice(name="Mania", value=3),
        ]
    )
    async def best(
        self,
        interaction: discord.Interaction,
        osu_user: str = None,
        mode: int = None,
        bp_rank: int = None,
    ):
        try:
            await interaction.response.defer()
            user_id_for_l10n = interaction.user.id

            if osu_user is None:
                bound_osu_user = await user_data_manager.get_user_binding(
                    user_id_for_l10n
                )
                if bound_osu_user:
                    osu_user = bound_osu_user
                else:
                    await interaction.followup.send(
                        lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound")
                    )
                    return

            player_data, error_msg = await self._get_user_data(
                str(osu_user).strip(), user_id_for_l10n
            )
            if error_msg:
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n, "error_user_not_found", str(osu_user).strip()
                    ),
                    ephemeral=True,
                )
                return

            numeric_user_id = player_data.get("id")
            player_name_for_embed = player_data.get("username") or str(osu_user).strip()
            player_avatar_url = player_data.get("avatar_url")

            actual_mode_int = await self._determine_game_mode(mode, player_data, "best")

            actual_mode_str = OSU_MODES_INT_TO_STRING.get(actual_mode_int)
            if actual_mode_str is None:  # Should not happen with choices
                await interaction.followup.send(
                    f"Internal error: Invalid game mode selected.", ephemeral=True
                )
                return

            # Fetch top 200 scores
            best_scores = await self.osu_api.get_user_best(
                user_id=str(numeric_user_id),
                mode=actual_mode_str,
                limit=200,  # Get all from the start, offset is a valid param for get_user_best for pagination if needed later
            )

            if not best_scores:
                error_msg_key = "error_no_best_plays"
                logger.debug(
                    f"[OSU_COG /best] No best plays found for user {player_name_for_embed} (ID: {numeric_user_id}) in mode {actual_mode_str}."
                )  # Added log
                await interaction.followup.send(
                    lstr(user_id_for_l10n, error_msg_key, "", player_name_for_embed),
                    ephemeral=True,
                )
                return

            logger.debug(
                f"[OSU_COG /best] Fetched {len(best_scores)} best plays for user {player_name_for_embed}."
            )  # Log actual fetched count
            if best_scores:
                logger.debug(
                    f"[OSU_COG /best] First best score data (mode: {actual_mode_str}): {str(best_scores[0])[:500]}..."
                )

            # 決定初始顯示的 BP 編號
            initial_index = 0
            if bp_rank is not None:
                if not (1 <= bp_rank <= len(best_scores)):
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_best_play_not_found",
                            bp_rank,
                            player_name_for_embed,
                        ),
                        ephemeral=True,
                    )
                    return
                initial_index = bp_rank - 1

            # Create initial embed for the selected score
            initial_embed = await self._create_score_embed(
                score_data=best_scores[initial_index],
                player_name=player_name_for_embed,
                player_avatar_url=player_avatar_url,
                mode_int=actual_mode_int,
                user_id_for_l10n=user_id_for_l10n,
                rank_in_top=initial_index + 1,  # BP rank (1-based)
            )

            # Create the view
            view = BestScoreView(
                cog_instance=self,
                scores=best_scores,
                osu_player_name=player_name_for_embed,
                player_avatar_url=player_avatar_url,
                mode_int=actual_mode_int,
                user_id_for_l10n=user_id_for_l10n,
            )
            view.current_index = initial_index

            message = await interaction.followup.send(embed=initial_embed, view=view)
            view.message = message

        except Exception as e:
            logger.error(
                f"[OSU_COG ERROR /best] Error in /best command: {type(e).__name__} - {e}",
                exc_info=True,
            )
            # Ensure a fallback if lstr fails during error reporting
            error_report_message = lstr(
                user_id_for_l10n, "error_generic_command", type(e).__name__
            )
            if "<translation_missing" in error_report_message:
                error_report_message = (
                    f"An unexpected error occurred: {type(e).__name__}"
                )
            await interaction.followup.send(error_report_message, ephemeral=True)

    async def _create_score_embed(
        self,
        score_data: dict,
        player_name: str,
        player_avatar_url: str,
        mode_int: int,
        user_id_for_l10n: int,
        rank_in_top: int = None,
    ) -> discord.Embed:
        # This function will create the embed for a single score (recent or best)
        # It needs to be adapted from the existing logic in /recent and /best
        logger.debug(
            f"[_create_score_embed] Called for player: {player_name}, mode_int: {mode_int}, rank_in_top: {rank_in_top}"
        )

        # Determine language for l10n based on user_id
        lang_code = get_user_language(str(user_id_for_l10n))
        # logger.debug(f"[_create_score_embed] Language for user {user_id_for_l10n} determined as: {lang_code}")

        beatmap_data = score_data.get("beatmap", {})
        beatmapset_data = score_data.get("beatmapset", {})
        beatmap_id = beatmap_data.get("id")
        beatmap_url = beatmap_data.get("url", f"https://osu.ppy.sh/b/{beatmap_id}")

        creator_name = beatmapset_data.get(
            "creator", lstr(user_id_for_l10n, "value_not_available", "N/A")
        )
        creator_id = beatmapset_data.get("user_id")  # For linking to creator profile

        beatmap_artist = beatmapset_data.get(
            "artist", lstr(user_id_for_l10n, "value_not_available", "N/A")
        )
        beatmap_title = beatmapset_data.get(
            "title", lstr(user_id_for_l10n, "value_not_available", "N/A")
        )
        beatmap_version = beatmap_data.get(
            "version", lstr(user_id_for_l10n, "value_not_available", "N/A")
        )

        mods_list = score_data.get("mods", [])
        # completion_emoji = get_completion_percentage_emoji( # REMOVED
        #    beatmap_data.get("hit_length", 0), # Playable length of the map
        #    score_data.get("total_length", 0), # How much of the map was played in the score (API v1 specific for fail time) - THIS IS USUALLY NOT AVAILABLE IN V2 SCORE
        #    score_data.get("passed", True) # if score has passed = True, False if failed. Default to True if not present
        # )

        mods_str_display = format_mods_for_display(
            mods_list
        )  # Use the imported function

        # Construct title
        # Example: " username - artist - title [version] +HDDT"
        # If rank_in_top is provided (for /best), use that l10n key. Otherwise, for /recent.
        title_key = (
            "best_embed_title" if rank_in_top is not None else "recent_embed_title"
        )
        # Fallback title formats
        english_fallback_title = (
            f"{player_name}'s Best #{rank_in_top}"
            if rank_in_top is not None
            else f"Recent play for {player_name}"
        )

        # The l10n keys for titles expect player_name and optionally rank_in_top
        if rank_in_top is not None:
            embed_title_template = lstr(
                user_id_for_l10n, title_key, english_fallback_title
            )
            try:
                embed_title = embed_title_template.format(player_name, rank_in_top)
            except IndexError:  # If template doesn't have two {}
                embed_title = embed_title_template.format(player_name)  # Try with one
        else:
            embed_title_template = lstr(
                user_id_for_l10n, title_key, english_fallback_title
            )
            embed_title = embed_title_template.format(player_name)

        # Beatmap part of the title: Artist - Title [Version] +Mods
        beatmap_display_in_title = f"{beatmap_artist} - {beatmap_title} [{beatmap_version}] {mods_str_display}".strip()

        embed_color = RANK_COLORS.get(
            score_data.get("rank", "F").upper(), discord.Color.default()
        )

        embed = discord.Embed(
            title=embed_title,  # This is "Player's Recent/Best"
            description=f"**[{beatmap_display_in_title}]({beatmap_url})**",  # Beatmap line as description
            color=embed_color,
        )
        if player_avatar_url:
            embed.set_author(
                name=player_name,
                icon_url=player_avatar_url,
                url=f"https://osu.ppy.sh/users/{score_data['user_id']}",
            )  # Use actual player_name for author too
        else:
            embed.set_author(
                name=player_name,
                url=f"https://osu.ppy.sh/users/{score_data['user_id']}",
            )

        # Score Details
        score_val = score_data.get("score", 0)  # Default from API v2
        acc_val = score_data.get("accuracy", 0.0) * 100
        combo_val = score_data.get("max_combo", 0)
        pp_val = score_data.get("pp")  # Can be None

        # --- Fallback to API v1 for score if API v2 returned 0 for a seemingly valid play ---
        v1_fallback_failed = False
        if score_val == 0 and pp_val is not None and pp_val > 0:
            logger.info(
                f"[_create_score_embed] API v2 score is 0 for a play with {pp_val} PP (Mode: {mode_int}). Attempting API v1 fallback."
            )
            beatmap_id_for_v1 = beatmap_data.get("id")
            user_id_for_v1 = score_data.get(
                "user_id"
            )  # This is the numeric user ID from API v2 response

            if beatmap_id_for_v1 and user_id_for_v1:
                try:
                    v1_score_data = await self.osu_api.get_score_v1(
                        beatmap_id=beatmap_id_for_v1,
                        user_id=user_id_for_v1,
                        mode=mode_int,
                    )
                    if v1_score_data and isinstance(v1_score_data, dict):
                        v1_score_val = v1_score_data.get("score")
                        if v1_score_val:
                            try:
                                score_val = int(v1_score_val)
                                logger.info(
                                    f"[_create_score_embed] Successfully updated score to {score_val} using API v1 fallback for beatmap {beatmap_id_for_v1}, user {user_id_for_v1}, mode {mode_int}."
                                )
                            except ValueError:
                                logger.warning(
                                    f"[_create_score_embed] Could not parse score '{v1_score_val}' from API v1 as int."
                                )
                        else:
                            logger.info(
                                f"[_create_score_embed] API v1 fallback did not return a 'score' value for beatmap {beatmap_id_for_v1}, user {user_id_for_v1}, mode {mode_int}."
                            )
                            v1_fallback_failed = True
                    else:
                        logger.info(
                            f"[_create_score_embed] API v1 fallback did not return valid score data for beatmap {beatmap_id_for_v1}, user {user_id_for_v1}, mode {mode_int}."
                        )
                        v1_fallback_failed = True
                except Exception as e_v1:
                    logger.error(
                        f"[_create_score_embed] Error during API v1 fallback: {e_v1}",
                        exc_info=True,
                    )
                    v1_fallback_failed = True
            else:
                v1_fallback_failed = True
        # --- End of API v1 Fallback ---

        mods_str = score_data.get("mods", [])
        if mods_str:
            mods_str = "".join(mods_str)
        else:
            mods_str = lstr(
                user_id_for_l10n, "mods_nomod", "No Mod"
            )  # Use new l10n key

        # Rank Emoji logic (copied and adapted from user_cog)
        rank_key = score_data.get("rank", "F").upper()
        if rank_key == "XH":
            final_rank_emoji = "<:rkhdfl:1373246417350561844>"
        elif rank_key == "SH":
            final_rank_emoji = "<:rkshdfl:1373964175671427143>"
        else:
            final_rank_emoji = RANK_EMOJI_MAP.get(rank_key, rank_key)

        # Special handling for SS/S with HD/FL (check mods)
        is_hd_fl_present = any(mod in mods_str for mod in ["HD", "FL"])
        if rank_key == "X" and is_hd_fl_present:  # SS HD/FL
            final_rank_emoji = "<:rkhdflss:1373246464522653727>"  # Placeholder
        elif rank_key == "S" and is_hd_fl_present:
            final_rank_emoji = "<:rkshdfl:1373964175671427143>"  # 銀色S emoji

        embed.add_field(
            name=lstr(user_id_for_l10n, "score_label", "Score"),
            value=f"{score_val:,}",
            inline=True,
        )  # Restored
        embed.add_field(
            name=lstr(user_id_for_l10n, "accuracy_label", "Accuracy"),
            value=f"{acc_val:.2f}%",
            inline=True,
        )
        embed.add_field(
            name=lstr(user_id_for_l10n, "rank_label", "Rank"),
            value=final_rank_emoji,
            inline=True,
        )

        # The next fields will start a new row if the above makes a full row of 3
        embed.add_field(
            name=lstr(user_id_for_l10n, "combo_label", "Combo"),
            value=f"{combo_val}x",
            inline=True,
        )
        embed.add_field(
            name=lstr(user_id_for_l10n, "mods_label", "Mods"),
            value=mods_str if mods_str else self.get_na_value(user_id_for_l10n),
            inline=True,
        )
        embed.add_field(
            name=lstr(user_id_for_l10n, "pp_label", "PP"),
            value=f"{pp_val:.2f}pp"
            if pp_val is not None
            else self.get_na_value(user_id_for_l10n),
            inline=True,
        )

        # Add Beatmap Status here, after PP, inline=True
        # beatmapset_data is already fetched
        raw_status_recent = beatmapset_data.get("status")  # Prefer API v2 string status
        if not isinstance(raw_status_recent, str):
            raw_status_recent = beatmapset_data.get(
                "ranked"
            )  # Fallback to integer status

        status_display_string_recent = get_beatmap_status_display(
            raw_status_recent,
            user_id_for_l10n,
            lambda uid, key, fallback: lstr(uid, key, fallback),
        )
        # Use the same l10n key as for /pp command for the field name, or a more generic one if preferred.
        # For now, let's use a generic "Status" key if pp_embed_beatmap_status is too specific, or reuse.
        # Reusing "pp_embed_beatmap_status" for consistency in what the field is called.
        embed.add_field(
            name=lstr(user_id_for_l10n, "pp_embed_beatmap_status", "Beatmap Status"),
            value=status_display_string_recent,
            inline=True,
        )

        # Game Mode
        game_mode_emoji = MODE_EMOJI_STRINGS.get(mode_int, "")
        game_mode_name = self.get_mode_name(mode_int, user_id_for_l10n, name_only=True)
        embed.add_field(
            name=lstr(user_id_for_l10n, "user_profile_game_mode", "Game Mode"),
            value=f"{game_mode_emoji} {game_mode_name}",
            inline=True,
        )

        # Hits (300s/100s/50s/misses for osu!std, adapt for others)
        # API v2 score object has a 'statistics' dictionary
        stats = score_data.get("statistics", {})
        hits_str = ""
        if mode_int == 0:  # osu!
            hits_str = f"{stats.get('count_300', 0)}/{stats.get('count_100', 0)}/{stats.get('count_50', 0)}/{stats.get('count_miss', 0)}"
        elif mode_int == 1:  # Taiko
            hits_str = f"{stats.get('count_300', 0)}/{stats.get('count_100', 0)}/{stats.get('count_miss', 0)}"
        elif mode_int == 2:  # Fruits
            # For Fruits (CTB), common stats are: count_300 (fruits), count_100 (droplets), count_50 (tiny droplets/missed small fruit), count_miss (missed large fruit)
            # API might use different keys, e.g. perfect, great, large_tick_hit, small_tick_hit, miss etc.
            # Based on typical API v2 responses, it should directly provide counts for fruits, droplets, and misses.
            # Let's assume the following, if direct keys aren't found, we'll see N/A or 0.
            # It's possible 'count_large_tick_hit', 'count_small_tick_hit', 'count_small_tick_miss' are used.
            # For now, let's stick to the generic ones from osu-wiki for display intent.
            # Actual API keys: perfect, great, good, ok, miss (for CTB, these map to 300,100,50,small_miss,miss)
            # The 'statistics' dict for CTB should have:
            # 'perfect': count_300 (fruits)
            # 'great': count_100 (droplets)
            # 'miss': count_miss (missed fruits)
            # 'good': count_50 (small droplets / tiny fruit) - often not displayed prominently.
            # Droplet misses (small_tick_miss) are sometimes separate.
            # For a clear display: Fruits / Droplets / Missed Fruits / (Optionally: Droplet Misses)
            # Using the direct mapping from score_data.statistics for fruits:
            # Example keys from API (ctb): 'great', 'large_tick_hit', 'miss', 'perfect', 'small_tick_hit', 'small_tick_miss'
            # Mapping for display:
            #   Fruits: perfect (count_300)
            #   Droplets: large_tick_hit (count_100)
            #   Small Droplets: small_tick_hit (count_50)
            #   Missed Fruits: miss
            #   Missed Droplets: small_tick_miss (often rolled into general accuracy or not shown)
            # Let's try a common display format: Fruits / Droplets / Small Droplets / Missed Fruits
            # The provided screenshot shows 1101/18/0/1 for std, so it's 300/100/50/miss. We should aim for consistency.
            # API docs state for CTB: "count_300", "count_100", "count_50", "count_miss", "count_katu" (katu is for droplets misses, not usually displayed)
            # Official API v2 "Score" object lists for mode "fruits":
            # statistics: count_50, count_100, count_300, count_miss, count_katu (missed tiny droplets)
            # So, the original: count_300 / count_100 / count_50 / count_miss should be correct from API.
            # The problem might be that for some users/scores, these fields are 0 or not present.
            hits_str = f"{stats.get('count_300', 0)}/{stats.get('count_100', 0)}/{stats.get('count_50', 0)}/{stats.get('count_miss', 0)}"
        elif mode_int == 3:  # Mania
            hits_str = f"{stats.get('count_geki', 0)}/{stats.get('count_300', 0)}/{stats.get('count_katu', 0)}/{stats.get('count_100', 0)}/{stats.get('count_50', 0)}/{stats.get('count_miss', 0)}"

        if hits_str:
            embed.add_field(
                name=lstr(user_id_for_l10n, "hits_label", "Hits"),
                value=hits_str,
                inline=True,
            )

        # Date
        created_at_str = score_data.get("created_at")
        footer_date_str = None
        if created_at_str:
            dt_object = datetime.datetime.fromisoformat(
                created_at_str.replace("Z", "+00:00")
            )
            # 不要設定 embed.timestamp，只組合 footer_date_str
            if lang_code == "zh_TW":
                footer_date_str = dt_object.strftime("%Y/%m/%d %H:%M")
            else:
                footer_date_str = dt_object.strftime("%Y-%m-%d %H:%M")

        # Beatmap Cover
        if beatmapset_data.get("covers", {}).get("cover"):
            embed.set_image(
                url=beatmapset_data.get("covers").get("cover")
            )  # Changed to set_image

        # --- Add footer note if score is 0 and v1 fallback failed ---
        footer_note = None
        if score_val == 0 and pp_val is not None and pp_val > 0 and v1_fallback_failed:
            footer_note = lstr(
                user_id_for_l10n,
                "score_footer_note_lazer",
                "※ This score may be unavailable due to Lazer or legacy plays",
            )
        # 組合 footer 文字
        footer_parts = []
        if footer_date_str:
            footer_parts.append(footer_date_str)
        if footer_note:
            footer_parts.append(footer_note)
        if footer_parts:
            embed.set_footer(text=" | ".join(footer_parts))
        # --- End footer note ---

        return embed


async def setup(bot: commands.Bot):
    # Add choices for mode parameter dynamically based on OSU_MODES and localization
    # This needs to be done carefully as app_commands.Choice needs to be defined at command definition time or transformed.
    # For now, I'll keep it simple and not dynamically localize choices. Users will see 0,1,2,3.
    # We can add a helper to generate choices with localized names if needed later.

    # For /recent mode choices
    # recent_command = OsuCog.recent # Get the command object
    # choices_list = []
    # Assuming interaction.locale can be accessed later, or we use a fixed set of choices for now
    # For simplicity at this stage, let's assume the choices are not localized in the command definition itself.
    # The display of the mode in the embed IS localized.
    # for val, key_name in OSU_MODES.items():
    # For initial setup, let's not make choices localized yet, as it's complex with app_commands
    # name = lstr(None, key_name) # This would need a context for user_id for l10n
    # choices_list.append(app_commands.Choice(name=key_name.replace("mode_","").capitalize(), value=val)) # Non-localized choice names

    # This is how you would typically add choices if they are static or can be prepared beforehand.
    # However, `app_commands.Choice` is usually part of the decorator.
    # For dynamic choices based on l10n for the choice name itself, it's more complex.
    # The current implementation of `mode: app_commands.Choice[int] = None` in the command
    # signature is not how choices are typically defined for slash commands.
    # It should be `mode: Optional[app_commands.Choice[int]] = None` and then # This comment is now outdated
    # `@app_commands.choices(mode=[...list of Choice objects...])`

    # Re-defining commands to correctly use app_commands.Choice
    # This is a bit tricky because the class methods are already defined.
    # The ideal way is to use @app_commands.choices in the decorator.
    # I will adjust the command definition directly.

    # Let's remove the dynamic choice generation from setup for now, and define choices in the decorator # This is now done.
    # If mode is not provided, it defaults to config.DEFAULT_OSU_MODE.
    # If mode is provided, it comes from the user's selection of the Choice.

    await bot.add_cog(OsuCog(bot))
    logger.info("OsuCog loaded.")
