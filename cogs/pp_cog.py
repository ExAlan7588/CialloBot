from __future__ import annotations

import pathlib
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils import beatmap_utils  # Import the new beatmap utils
from utils.beatmap_utils import get_beatmap_status_display  # IMPORT THE NEW FUNCTION
from utils.localization import (
    get_localized_string as lstr,
)  # Assuming you might use localization later

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI


# --- Helper function to format mods for display ---
def format_mods_for_display(mod_list: list[str]) -> str:
    if not mod_list:
        return ""
    return "+" + "".join(mod_list).upper()


# --- Mod Select UI Elements ---
class ModSelect(discord.ui.Select):
    def __init__(self, parent_view, available_mods) -> None:
        self.parent_view = parent_view
        options = [discord.SelectOption(label=mod.upper(), value=mod) for mod in available_mods]
        # Add "No Mods" option
        options.insert(0, discord.SelectOption(label="-- No Mods --", value="_no_mods_"))

        if not options:
            options = [
                discord.SelectOption(label="No Mods Available", value="_disabled", default=True)
            ]
            super().__init__(
                placeholder="No mods applicable...",
                min_values=0,
                max_values=1,
                options=options,
                disabled=True,
            )
        else:
            super().__init__(
                placeholder="Select mods...",
                min_values=0,
                max_values=len(available_mods),
                options=options,
            )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.update_embed_with_mods(interaction, self.values)


class ModSelectView(discord.ui.View):
    def __init__(
        self,
        cog_instance,
        beatmap_id: int,
        current_ruleset_id: int,
        target_beatmap: dict,
        beatmapset_data: dict,
        user_id_for_l10n: str,
        all_maps_in_set: list | None = None,
        current_difficulty_index: int | None = None,
    ) -> None:
        super().__init__(timeout=300)  # 5 minutes
        self.cog = cog_instance
        self.osu_api: OsuAPI = cog_instance.osu_api
        self.beatmap_id = beatmap_id  # This will be the initially selected beatmap_id
        self.current_ruleset_id = current_ruleset_id
        self.target_beatmap = target_beatmap  # Initially selected beatmap object
        self.beatmapset_data = beatmapset_data
        self.user_id_for_l10n = user_id_for_l10n
        self.selected_mods = []  # Store currently selected mods, always start with no mods for pp command

        self.all_maps_in_set = all_maps_in_set
        self.current_difficulty_index = current_difficulty_index

        # Define available mods (can be dynamic based on ruleset_id later)
        # For now, a generic list suitable for osu!std, taiko, ctb
        self.available_mods = ["HD", "HR", "DT", "FL", "EZ", "HT", "NF"]

        self.mod_select_menu = ModSelect(self, self.available_mods)
        self.add_item(self.mod_select_menu)

        if self.all_maps_in_set and self.current_difficulty_index is not None:
            # If pagination is active, add pagination buttons
            prev_label = lstr(self.user_id_for_l10n, "button_prev_difficulty", "⬅️ Prev Diff")
            self.prev_difficulty_button = discord.ui.Button(
                label=prev_label, style=discord.ButtonStyle.secondary, row=1
            )
            self.prev_difficulty_button.callback = self.prev_difficulty_callback
            self.add_item(self.prev_difficulty_button)

            next_label = lstr(self.user_id_for_l10n, "button_next_difficulty", "Next Diff ➡️")
            self.next_difficulty_button = discord.ui.Button(
                label=next_label, style=discord.ButtonStyle.secondary, row=1
            )
            self.next_difficulty_button.callback = self.next_difficulty_callback
            self.add_item(self.next_difficulty_button)

            self._update_pagination_buttons_state()  # Initial state update

    def _update_pagination_buttons_state(self) -> None:
        if not self.all_maps_in_set or self.current_difficulty_index is None:
            if hasattr(self, "prev_difficulty_button"):
                self.prev_difficulty_button.disabled = True
            if hasattr(self, "next_difficulty_button"):
                self.next_difficulty_button.disabled = True
            return

        if self.current_difficulty_index == 0:
            self.prev_difficulty_button.disabled = True
        else:
            self.prev_difficulty_button.disabled = False

        if self.current_difficulty_index == len(self.all_maps_in_set) - 1:
            self.next_difficulty_button.disabled = True
        else:
            self.next_difficulty_button.disabled = False

    async def prev_difficulty_callback(self, interaction: discord.Interaction) -> None:
        if (
            self.all_maps_in_set
            and self.current_difficulty_index is not None
            and self.current_difficulty_index > 0
        ):
            self.current_difficulty_index -= 1
            await self._update_difficulty(interaction)

    async def next_difficulty_callback(self, interaction: discord.Interaction) -> None:
        if (
            self.all_maps_in_set
            and self.current_difficulty_index is not None
            and self.current_difficulty_index < len(self.all_maps_in_set) - 1
        ):
            self.current_difficulty_index += 1
            await self._update_difficulty(interaction)

    async def _update_difficulty(self, interaction: discord.Interaction) -> None:
        # This method will be called by prev/next callbacks
        await interaction.response.defer()  # Defer interaction

        self.target_beatmap = self.all_maps_in_set[self.current_difficulty_index]
        self.beatmap_id = self.target_beatmap.get("id")
        # IMPORTANT: As per user choice, clear selected mods when difficulty changes
        self.selected_mods = []
        # Reset the visual state of the ModSelect dropdown to show "No Mods"
        # This is a bit tricky as the Select object doesn't have a direct "clear_selection"
        # We might need to re-create the select or find a way to tell it to reset its placeholder/default.
        # For now, the internal self.selected_mods is cleared, which is what matters for PP calculation.
        # Visually, the dropdown might retain old selection until user interacts.
        # A better way would be to re-construct the ModSelect or the entire View, but that's more complex.

        # Update ruleset ID based on the new target_beatmap
        ruleset_id_map = {
            "osu": 0,
            "taiko": 1,
            "fruits": 2,
            "mania": 3,
        }  # Duplicated from pp method, maybe move to class/cog level
        self.current_ruleset_id = ruleset_id_map.get(self.target_beatmap.get("mode"), 0)

        new_attributes = await self.osu_api.get_beatmap_attributes(
            beatmap_id=self.beatmap_id,
            mods=[],  # Always fetch NoMod for new difficulty
            ruleset_id=self.current_ruleset_id,
        )

        if not new_attributes or "attributes" not in new_attributes:
            await interaction.followup.send(
                lstr(
                    self.user_id_for_l10n,
                    "error_beatmap_attributes_not_found",
                    "Could not retrieve beatmap attributes for the new difficulty.",
                ),
                ephemeral=True,
            )
            return

        new_embed = await self.cog._generate_pp_embed(
            interaction=interaction,
            target_beatmap=self.target_beatmap,
            beatmapset_data=self.beatmapset_data,  # Beatmapset data remains the same
            beatmap_attributes_response=new_attributes,
            user_id_for_l10n=self.user_id_for_l10n,
            selected_mods_list=[],  # Always NoMod for new difficulty
        )

        self._update_pagination_buttons_state()  # Update button states before sending

        # We need to re-create the ModSelect menu if its options depend on the ruleset
        # or if we want to force a visual reset.
        # For now, just re-adding the existing menu.
        # A more robust solution might involve rebuilding the ModSelect part of the view.
        # If its options change, we MUST remove the old one and add a new one.
        # For now, assuming available_mods list is static.

        # If we want to truly reset the ModSelect menu visual state, we would do:
        # self.remove_item(self.mod_select_menu)
        # self.mod_select_menu = ModSelect(self, self.available_mods) # Recreate
        # self.add_item(self.mod_select_menu)
        # However, this changes item order if pagination buttons are row 1.
        # Let's try to handle visual reset later if it becomes a major issue.

        await interaction.edit_original_response(embed=new_embed, view=self)

    async def update_embed_with_mods(
        self, interaction: discord.Interaction, selected_mods: list[str]
    ) -> None:
        await interaction.response.defer()  # Defer if calculation takes time

        # Handle "No Mods" selection
        if "_no_mods_" in selected_mods:
            self.selected_mods = []  # Clear mods
            # If "No Mods" is selected along with other mods, typically we'd clear all.
            # Or, one could make it an exclusive choice, but this is simpler for multi-select.
        else:
            self.selected_mods = selected_mods  # Update stored mods

        new_attributes = await self.osu_api.get_beatmap_attributes(
            beatmap_id=self.beatmap_id,
            mods=self.selected_mods,  # Use the potentially cleared list
            ruleset_id=self.current_ruleset_id,
        )

        if not new_attributes or "attributes" not in new_attributes:
            # Try to send an ephemeral message. If interaction already responded, this might fail.
            # Consider logging instead or a more robust error feedback.
            try:
                await interaction.followup.send(
                    lstr(
                        self.user_id_for_l10n,
                        "error_beatmap_attributes_not_found",
                        "Could not retrieve beatmap attributes with selected mods.",
                    ),
                    ephemeral=True,
                )
            except discord.HTTPException:
                logger.error(
                    f"[PP_COG] Failed to send followup for attribute error after mod selection. Interaction: {interaction.id}"
                )
            return

        new_embed = await self.cog._generate_pp_embed(
            interaction=interaction,
            target_beatmap=self.target_beatmap,
            beatmapset_data=self.beatmapset_data,
            beatmap_attributes_response=new_attributes,
            user_id_for_l10n=self.user_id_for_l10n,
            selected_mods_list=self.selected_mods,  # Pass the processed list
        )

        # Edit the original message with the new embed and the same view
        await interaction.edit_original_response(embed=new_embed, view=self)


class PpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client

    async def _generate_pp_embed(
        self,
        interaction: discord.Interaction,
        target_beatmap: dict,
        beatmapset_data: dict,
        beatmap_attributes_response: dict,
        user_id_for_l10n: str,
        selected_mods_list: list[str] | None = None,
    ):
        if selected_mods_list is None:
            selected_mods_list = []

        # These might be overwritten if .osu file is parsed
        artist = beatmapset_data.get("artist", "Unknown Artist")
        title = beatmapset_data.get("title", "Unknown Title")
        version = target_beatmap.get("version", "Unknown Difficulty")
        current_map_mode = target_beatmap.get("mode", "osu")

        mod_string_display = format_mods_for_display(selected_mods_list)

        attributes_data = beatmap_attributes_response.get("attributes", {})

        cs = attributes_data.get("circle_size")
        if cs is None:
            cs = target_beatmap.get("cs", "N/A")
        ar = attributes_data.get("approach_rate")
        if ar is None:
            ar = target_beatmap.get("ar", "N/A")
        hp = attributes_data.get("hp_drain")
        if hp is None:
            hp = target_beatmap.get("drain", "N/A")
        od = attributes_data.get("accuracy")
        if od is None:
            od = target_beatmap.get("accuracy", "N/A")

        # Get beatmap status from beatmapset_data
        # Prefer 'status' (string like "ranked", "loved") if available (usually from API v2 beatmapset object)
        # Fallback to 'ranked' (integer like 1, 4) if 'status' is not present or not a string
        raw_status = beatmapset_data.get("status")
        if not isinstance(
            raw_status, str
        ):  # If 'status' is not a string (e.g. it's an int or None)
            raw_status = beatmapset_data.get("ranked")  # Try 'ranked' integer field

        # If still no valid status, it will be handled by get_beatmap_status_display as "unknown"
        # The lstr function is available in this scope via self.bot.l10n.get_lstr_value
        # but _generate_pp_embed is part of the cog, so self.bot.l10n... or pass lstr
        # lstr is already available in the calling scope of pp command, let's ensure it's passed or accessible
        # User ID for l10n is already available as user_id_for_l10n

        status_display_string = get_beatmap_status_display(raw_status, user_id_for_l10n, lstr)

        stars_raw = attributes_data.get("star_rating")
        pp_100_raw = attributes_data.get("pp")
        max_combo_from_api_attrs = attributes_data.get("max_combo")  # From /attributes POST
        if max_combo_from_api_attrs is None:  # Fallback to beatmap details if not in /attributes
            max_combo_from_api_attrs = target_beatmap.get("max_combo")

        osu_file_path = None  # To store path of downloaded .osu file
        used_rosu_pp = False
        rosu_pp_error_message_key = None  # Key for localization string

        # If API doesn't provide PP (e.g., with certain mods), try rosu-pp
        if pp_100_raw is None:  # Try for any mode if API doesn't provide PP
            # Ensure session is available
            if hasattr(self.osu_api, "session") and self.osu_api.session is not None:
                beatmap_id_for_download = target_beatmap.get("id")
                if beatmap_id_for_download:
                    logger.debug(
                        f"[PpCog] API did not return PP. Attempting download and rosu-pp for beatmap ID: {beatmap_id_for_download}"
                    )
                    try:
                        osu_file_path = await beatmap_utils.download_osu_file(
                            beatmap_id_for_download, self.osu_api.session
                        )
                        # No need to check if osu_file_path is None, as download_osu_file now raises on error.

                        # Parse metadata from .osu file and use it
                        parsed_metadata = beatmap_utils.parse_osu_file_metadata(osu_file_path)
                        artist = parsed_metadata.get("artist", artist)
                        title = parsed_metadata.get("title", title)
                        version = parsed_metadata.get("version", version)
                        logger.debug(
                            f"[PpCog] Using metadata from .osu: {artist} - {title} [{version}]"
                        )

                        rosu_pp_result = await beatmap_utils.calculate_pp_with_rosu(
                            osu_file_path, selected_mods_list, accuracy=100.0, combo=None, misses=0
                        )
                        # No need to check if rosu_pp_result is None, as calculate_pp_with_rosu now raises on error.

                        pp_100_raw = rosu_pp_result.get("pp")
                        stars_raw = rosu_pp_result.get("stars")
                        max_combo_from_api_attrs = rosu_pp_result.get("max_combo")
                        logger.debug(
                            f"[PpCog] rosu-pp calculated: PP={pp_100_raw}, Stars={stars_raw}"
                        )
                        used_rosu_pp = True

                    except beatmap_utils.BeatmapDownloadError as e:
                        logger.error(f"[PpCog] Error downloading .osu file: {e}")
                        rosu_pp_error_message_key = "error_beatmap_download_failed"
                    except beatmap_utils.RosuPpCalculationError as e:
                        logger.error(f"[PpCog] Error calculating PP with rosu-pp: {e}")
                        rosu_pp_error_message_key = "error_rosupp_calculation_failed"
                    except Exception as e:  # Catch any other unexpected errors during this block
                        logger.error(
                            f"[PpCog] Unexpected error during rosu-pp processing: {type(e).__name__} - {e}"
                        )
                        rosu_pp_error_message_key = "error_rosupp_unexpected"
                    finally:
                        if osu_file_path and pathlib.Path(osu_file_path).exists():
                            beatmap_utils.delete_osu_file(osu_file_path)
            else:
                logger.warning("[PpCog] osu_api.session not available for .osu download.")
                # This case might also warrant a user-facing message if it implies rosu-pp cannot be attempted.
                # For now, it only logs.

        # Prepare footer text if rosu-pp was used
        footer_text = None
        if used_rosu_pp:
            footer_text = "PP via rosu-pp"

        # Title no longer includes rosu-pp indicator
        embed_title = f"{artist} - {title} [{version}] {mod_string_display}".strip()

        # Mode-specific attribute display adjustments (cs, ar, hp, od)
        cs_display = cs
        ar_display = ar
        hp_display = hp
        od_display = od
        key_display_line = ""

        if current_map_mode == "taiko":
            cs_display = "N/A"
            ar_display = "N/A"
        elif current_map_mode == "mania":
            ar_display = "N/A"
            key_display_line = f"Key: `{cs}` "
            cs_display = "N/A"

        attributes_line = (
            f"CS: `{cs_display}` AR: `{ar_display}` HP: `{hp_display}` OD: `{od_display}`".strip()
        )
        if key_display_line:
            attributes_line = f"{key_display_line}{attributes_line}"

        length_seconds = target_beatmap.get("total_length", 0)
        bpm = target_beatmap.get("bpm", "N/A")
        # If stars_raw is still None after API and rosu-pp, default to N/A for display
        stars_raw = stars_raw if stars_raw is not None else "N/A"

        minutes = length_seconds // 60
        seconds = length_seconds % 60
        formatted_length = f"{minutes}:{seconds:02d}"

        if isinstance(stars_raw, (int, float)):
            stars_display = f"{stars_raw:.2f}★"
        else:
            stars_display = f"{stars_raw}★"  # If it became "N/A" string

        if isinstance(pp_100_raw, (int, float)):
            pp_100_display = f"{pp_100_raw:.2f}pp"
        else:  # pp_100_raw is still None after API and potential rosu-pp attempt
            # The specific error for rosu-pp failure is handled by the ephemeral message.
            # Here, we just need a generic placeholder if PP is not available.
            pp_100_display = lstr(user_id_for_l10n, "pp_value_not_available", "N/A")

        embed = discord.Embed(
            title=embed_title, url=target_beatmap.get("url"), color=discord.Color.blue()
        )

        cover_url = beatmapset_data.get("covers", {}).get("cover")
        if cover_url:  # Change to set_image for bottom display
            embed.set_image(url=cover_url)

        if footer_text:  # Set footer if rosu-pp was used
            embed.set_footer(text=footer_text)

        # Add Beatmap Status field FIRST
        embed.add_field(
            name=lstr(user_id_for_l10n, "pp_embed_beatmap_status", "Beatmap Status"),
            value=status_display_string,
            inline=False,
        )

        embed.add_field(
            name=lstr(user_id_for_l10n, "pp_embed_attributes", "Attributes"),
            value=attributes_line,
            inline=False,
        )

        # Construct Map Info line (Length, BPM, Stars)
        map_info_parts = [
            f"Length: `{formatted_length}`",
            f"BPM: `{bpm}`",
            f"Stars: `{stars_display}`",
        ]
        embed.add_field(
            name=lstr(user_id_for_l10n, "pp_embed_map_info", "Map Info"),
            value=" ".join(map_info_parts),
            inline=False,
        )

        # PP (100%) field (now separate)
        pp_100_field_name = lstr(user_id_for_l10n, "pp_100_percent", "PP (100%)")
        pp_value_string = pp_100_display  # This already contains N/A if not available

        if used_rosu_pp:  # Suffix for estimation if rosu-pp was used
            estimated_suffix = lstr(user_id_for_l10n, "pp_estimated_suffix", "(估算值)")
            pp_100_field_name += f" {estimated_suffix}"  # Add to field name for clarity

        embed.add_field(name=pp_100_field_name, value=f"`{pp_value_string}`", inline=False)

        # If there was an error during rosu-pp processing, send a follow-up message
        if rosu_pp_error_message_key:
            try:
                # Check if interaction is already responded to or deferred.
                # If `_generate_pp_embed` is called after `interaction.response.defer()` or `interaction.edit_original_response()`,
                # then `followup.send` is appropriate.
                # If it's part of the initial response preparation before defer/send, this approach might need adjustment.
                # Given the structure, it's usually called after a defer.
                if interaction.is_expired():
                    logger.warning(
                        f"[PpCog] Interaction expired, cannot send rosu-pp error followup for key: {rosu_pp_error_message_key}"
                    )
                elif interaction.response.is_done():
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            rosu_pp_error_message_key,
                            "An error occurred during local PP calculation.",
                        ),
                        ephemeral=True,
                    )
                else:
                    # This case should ideally not happen if defer() was called.
                    # If it does, it means the main response hasn't been sent.
                    # For simplicity, we'll log and assume followup is the primary path.
                    logger.warning(
                        f"[PpCog] Warning: Interaction not yet responded or deferred when trying to send rosu-pp error. Key: {rosu_pp_error_message_key}"
                    )
                    # As a fallback, if no response has been sent, you *could* edit the original message to include the error,
                    # or send a regular message if followup isn't possible.
                    # However, given typical command flow, followup is expected.

            except discord.HTTPException as http_e:
                logger.error(
                    f"[PpCog] Failed to send rosu-pp error followup message (key: {rosu_pp_error_message_key}): {http_e}"
                )
            except Exception as e:
                logger.error(
                    f"[PpCog] Generic exception sending rosu-pp error followup (key: {rosu_pp_error_message_key}): {e}"
                )

        return embed

    @app_commands.command(name="pp", description="Shows PP information for an osu! beatmap.")
    @app_commands.describe(
        url="The URL of the osu! beatmap (either beatmapset or specific difficulty)."
    )
    async def pp(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer()
        user_id_for_l10n = interaction.user.id

        beatmap_id = None
        beatmapset_id = None

        match_beatmapset_diff = re.search(
            r"beatmapsets/(\d+)(?:#(osu|taiko|fruits|mania)/(\d+))?", url
        )
        match_beatmap_short = re.search(r"osu.ppy.sh/b/(\d+)", url)
        match_beatmapset_short = re.search(r"osu.ppy.sh/s/(\d+)", url)

        if match_beatmapset_diff:
            beatmapset_id = int(match_beatmapset_diff.group(1))
            if match_beatmapset_diff.group(3):
                beatmap_id = int(match_beatmapset_diff.group(3))
        elif match_beatmap_short:
            beatmap_id = int(match_beatmap_short.group(1))
        elif match_beatmapset_short:
            beatmapset_id = int(match_beatmapset_short.group(1))
        else:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "error_invalid_beatmap_url",
                    "Invalid osu! beatmap URL format.",
                )
            )
            return

        target_beatmap = None
        beatmapset_data = None
        all_maps_in_set_for_pagination = None  # For pagination
        initial_difficulty_index = 0  # Default for beatmapset case

        try:
            # Define sort_key once here to be used by both branches
            def sort_key(bm):
                mode_priority = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}
                # Sort by mode, then by difficulty_rating ASCENDING (Easy -> Hard)
                return (mode_priority.get(bm.get("mode"), 4), float(bm.get("difficulty_rating", 0)))

            if beatmap_id:  # Specific difficulty URL
                if not beatmapset_id:
                    temp_beatmap_details = await self.osu_api.get_beatmap_details(
                        beatmap_id=beatmap_id
                    )
                    if not temp_beatmap_details or not temp_beatmap_details.get("beatmapset_id"):
                        await interaction.followup.send(
                            lstr(
                                user_id_for_l10n,
                                "error_beatmap_data_incomplete",
                                "Could not retrieve beatmapset ID for the given difficulty.",
                            )
                        )
                        return
                    beatmapset_id = temp_beatmap_details.get("beatmapset_id")

                beatmapset_data = await self.osu_api.get_beatmapset(beatmapset_id=beatmapset_id)
                if not beatmapset_data or not beatmapset_data.get("beatmaps"):
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_beatmapset_not_found_api",
                            "Could not find the beatmapset or it has no maps.",
                        )
                    )
                    return

                raw_maps_from_set = beatmapset_data.get("beatmaps", [])
                if not raw_maps_from_set:
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_no_maps_in_set",
                            "Beatmapset contains no difficulties.",
                        )
                    )
                    return

                all_maps_in_set_for_pagination = sorted(raw_maps_from_set, key=sort_key)

                try:
                    # Find the index of the initially specified beatmap_id in the NEW sorted list
                    initial_difficulty_index = next(
                        i
                        for i, bm in enumerate(all_maps_in_set_for_pagination)
                        if bm.get("id") == beatmap_id
                    )
                except StopIteration:
                    logger.warning(
                        f"[PpCog] beatmap_id {beatmap_id} not found in its own sorted beatmapset (ascending sort). Defaulting to index 0."
                    )
                    initial_difficulty_index = 0  # Fallback, though ideally should always be found

                if initial_difficulty_index >= len(
                    all_maps_in_set_for_pagination
                ):  # Should not happen with StopIteration logic
                    initial_difficulty_index = 0

                target_beatmap = all_maps_in_set_for_pagination[initial_difficulty_index]
                # beatmap_id is the one user requested, ensure target_beatmap reflects this specific one.

            elif beatmapset_id:  # Beatmapset URL (no specific difficulty initially)
                beatmapset_data = await self.osu_api.get_beatmapset(beatmapset_id=beatmapset_id)
                if not beatmapset_data or not beatmapset_data.get("beatmaps"):
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_beatmapset_not_found_api",
                            "Could not find the specified beatmapset or it has no maps.",
                        )
                    )
                    return

                raw_maps_from_set = beatmapset_data.get("beatmaps", [])
                if not raw_maps_from_set:
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_no_maps_in_set",
                            "Beatmapset contains no difficulties.",
                        )
                    )
                    return

                all_maps_in_set_for_pagination = sorted(raw_maps_from_set, key=sort_key)

                if not all_maps_in_set_for_pagination:
                    await interaction.followup.send(
                        lstr(
                            user_id_for_l10n,
                            "error_no_maps_in_set",
                            "Error processing difficulties in beatmapset.",
                        )
                    )
                    return

                initial_difficulty_index = (
                    0  # For beatmapset URL, start with the first (easiest after sort)
                )
                target_beatmap = all_maps_in_set_for_pagination[initial_difficulty_index]
                beatmap_id = target_beatmap.get(
                    "id"
                )  # Update beatmap_id to reflect the initial target
            else:
                # This case should ideally be caught by the initial URL parsing.
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n,
                        "error_invalid_beatmap_url",
                        "Could not determine beatmap/beatmapset ID from URL.",
                    )
                )
                return

            if not target_beatmap or not beatmapset_data or not beatmap_id:
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n,
                        "error_beatmap_data_incomplete",
                        "Could not retrieve complete beatmap data.",
                    )
                )
                return

            ruleset_id_map = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}
            current_ruleset_id = ruleset_id_map.get(target_beatmap.get("mode"), 0)

            # Initial attributes (no mods)
            initial_beatmap_attributes = await self.osu_api.get_beatmap_attributes(
                beatmap_id=beatmap_id, mods=[], ruleset_id=current_ruleset_id
            )

            if not initial_beatmap_attributes or "attributes" not in initial_beatmap_attributes:
                await interaction.followup.send(
                    lstr(
                        user_id_for_l10n,
                        "error_beatmap_attributes_not_found",
                        "Could not retrieve initial beatmap attributes.",
                    )
                )
                return

            initial_embed = await self._generate_pp_embed(
                interaction=interaction,
                target_beatmap=target_beatmap,
                beatmapset_data=beatmapset_data,
                beatmap_attributes_response=initial_beatmap_attributes,
                user_id_for_l10n=user_id_for_l10n,
                selected_mods_list=[],  # Initially no mods
            )

            # Pass pagination related data to the view
            view = ModSelectView(
                self,
                beatmap_id,
                current_ruleset_id,
                target_beatmap,
                beatmapset_data,
                user_id_for_l10n,
                all_maps_in_set=all_maps_in_set_for_pagination,  # Can be None if specific diff
                current_difficulty_index=initial_difficulty_index,  # Can be None
            )
            await interaction.followup.send(embed=initial_embed, view=view)

        except Exception as e:
            logger.exception(f"Error in /pp command: {type(e).__name__} - {e}")
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "error_generic_command",
                    f"An unexpected error occurred: {type(e).__name__}",
                )
            )


async def setup(bot: commands.Bot) -> None:
    # Ensure the utils.beatmap_utils can be loaded correctly
    # And that rosu-pp-py is installed if calculate_pp_with_rosu is to be used.
    # The dynamic import in beatmap_utils will print an error if not found.
    await bot.add_cog(PpCog(bot))
    logger.info("PpCog loaded.")


# Example new localization strings to add to locales/en.json and locales/zh_TW.json:
# "pp_not_applicable_for_mode": "N/A (PP for this mode)",
# "pp_unavailable": "N/A (PP unavailable)",
# "pp_embed_attributes": "Attributes",
# "pp_embed_map_info": "Map Info",
# "pp_embed_pp_at_accuracy": "PP @ Accuracy",
# "common_tbd": "TBD"

# Placeholder localizations needed in your JSON files:
# "error_invalid_beatmap_url": "無效的 osu! 圖譜 URL 格式。",
# "error_beatmap_not_found_api": "找不到指定的圖譜難度。",
# "error_beatmapset_not_found_api": "找不到指定的圖譜集。",
# "error_no_maps_in_set": "此圖譜集不包含任何難度。",
# "error_beatmap_data_incomplete": "無法檢索完整的圖譜資料。",
# "error_beatmap_attributes_not_found": "無法檢索圖譜屬性。",
# "error_generic_command": "指令執行時發生未預期的錯誤: {}"
