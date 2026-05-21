from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import discord

from utils.localization import get_localized_string as lstr
from utils.osu_api import RULESET_IDS

from .pp_embed_builder import PpEmbedBuilder, PpEmbedRequest, PpEmbedResult

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI


AVAILABLE_MODS = ["HD", "HR", "DT", "FL", "EZ", "HT", "NF"]
NO_MODS_VALUE = "_no_mods_"
PP_VIEW_TIMEOUT_SECONDS = 300


class RosuErrorNotifier(Protocol):
    async def __call__(
        self, interaction: discord.Interaction, user_id_for_l10n: int, error_key: str
    ) -> None:
        """Send a user-facing rosu-pp error notification."""
        ...


@dataclass(frozen=True, kw_only=True)
class PpViewConfig:
    osu_api: OsuAPI
    embed_builder: PpEmbedBuilder
    rosu_error_notifier: RosuErrorNotifier
    beatmap_id: int
    current_ruleset_id: int
    target_beatmap: dict[str, Any]
    beatmapset_data: dict[str, Any]
    user_id_for_l10n: int
    all_maps_in_set: list[dict[str, Any]] | None
    current_difficulty_index: int | None


class ModSelect(discord.ui.Select):
    def __init__(self, parent_view: ModSelectView, available_mods: list[str]) -> None:
        self.parent_view = parent_view
        options = [discord.SelectOption(label=mod.upper(), value=mod) for mod in available_mods]
        options.insert(0, discord.SelectOption(label="-- No Mods --", value=NO_MODS_VALUE))
        super().__init__(
            placeholder="Select mods...",
            min_values=0,
            max_values=len(available_mods),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.update_embed_with_mods(interaction, list(self.values))


class ModSelectView(discord.ui.View):
    def __init__(self, config: PpViewConfig) -> None:
        super().__init__(timeout=PP_VIEW_TIMEOUT_SECONDS)
        self.config = config
        self.osu_api = config.osu_api
        self.embed_builder = config.embed_builder
        self.beatmap_id = config.beatmap_id
        self.current_ruleset_id = config.current_ruleset_id
        self.target_beatmap = config.target_beatmap
        self.beatmapset_data = config.beatmapset_data
        self.user_id_for_l10n = config.user_id_for_l10n
        self.selected_mods: list[str] = []
        self.all_maps_in_set = config.all_maps_in_set
        self.current_difficulty_index = config.current_difficulty_index

        self.mod_select_menu = ModSelect(self, AVAILABLE_MODS)
        self.add_item(self.mod_select_menu)
        self._add_pagination_buttons()

    def _add_pagination_buttons(self) -> None:
        if self.all_maps_in_set is None or self.current_difficulty_index is None:
            return

        self.prev_difficulty_button = discord.ui.Button(
            label=lstr(self.user_id_for_l10n, "button_prev_difficulty", "⬅️ Prev Diff"),
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.next_difficulty_button = discord.ui.Button(
            label=lstr(self.user_id_for_l10n, "button_next_difficulty", "Next Diff ➡️"),
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.prev_difficulty_button.callback = self.prev_difficulty_callback
        self.next_difficulty_button.callback = self.next_difficulty_callback
        self.add_item(self.prev_difficulty_button)
        self.add_item(self.next_difficulty_button)
        self._update_pagination_buttons_state()

    def _update_pagination_buttons_state(self) -> None:
        if self.all_maps_in_set is None or self.current_difficulty_index is None:
            return

        self.prev_difficulty_button.disabled = self.current_difficulty_index == 0
        self.next_difficulty_button.disabled = (
            self.current_difficulty_index >= len(self.all_maps_in_set) - 1
        )

    async def prev_difficulty_callback(self, interaction: discord.Interaction) -> None:
        if self.current_difficulty_index is None or self.current_difficulty_index == 0:
            await interaction.response.defer()
            return

        self.current_difficulty_index -= 1
        await self._update_difficulty(interaction)

    async def next_difficulty_callback(self, interaction: discord.Interaction) -> None:
        if not self._can_move_next():
            await interaction.response.defer()
            return

        self.current_difficulty_index += 1
        await self._update_difficulty(interaction)

    def _can_move_next(self) -> bool:
        return (
            self.all_maps_in_set is not None
            and self.current_difficulty_index is not None
            and self.current_difficulty_index < len(self.all_maps_in_set) - 1
        )

    async def _update_difficulty(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self._select_current_difficulty()
        attributes = await self._fetch_attributes([])
        if not _has_attributes(attributes):
            await _send_attributes_error(interaction, self.user_id_for_l10n)
            return

        result = await self._build_embed(attributes, [])
        self._update_pagination_buttons_state()
        await interaction.edit_original_response(embed=result.embed, view=self)
        await self._send_rosu_error(interaction, result.rosu_error_key)

    def _select_current_difficulty(self) -> None:
        if self.all_maps_in_set is None or self.current_difficulty_index is None:
            return

        self.target_beatmap = self.all_maps_in_set[self.current_difficulty_index]
        self.beatmap_id = _require_beatmap_id(self.target_beatmap)
        self.current_ruleset_id = RULESET_IDS.get(self.target_beatmap.get("mode"), 0)
        self.selected_mods = []

    async def update_embed_with_mods(
        self, interaction: discord.Interaction, selected_mods: list[str]
    ) -> None:
        await interaction.response.defer()
        self.selected_mods = [] if NO_MODS_VALUE in selected_mods else selected_mods
        attributes = await self._fetch_attributes(self.selected_mods)
        if not _has_attributes(attributes):
            await _send_attributes_error(interaction, self.user_id_for_l10n)
            return

        result = await self._build_embed(attributes, self.selected_mods)
        await interaction.edit_original_response(embed=result.embed, view=self)
        await self._send_rosu_error(interaction, result.rosu_error_key)

    async def _fetch_attributes(self, mods: list[str]) -> dict[str, Any]:
        return await self.osu_api.get_beatmap_attributes(
            beatmap_id=self.beatmap_id, mods=mods, ruleset_id=self.current_ruleset_id
        )

    async def _build_embed(
        self, attributes: dict[str, Any], selected_mods: list[str]
    ) -> PpEmbedResult:
        return await self.embed_builder.create(
            PpEmbedRequest(
                target_beatmap=self.target_beatmap,
                beatmapset_data=self.beatmapset_data,
                beatmap_attributes_response=attributes,
                user_id_for_l10n=self.user_id_for_l10n,
                selected_mods=selected_mods,
            )
        )

    async def _send_rosu_error(
        self, interaction: discord.Interaction, error_key: str | None
    ) -> None:
        if error_key is not None:
            await self.config.rosu_error_notifier(interaction, self.user_id_for_l10n, error_key)


def _require_beatmap_id(beatmap: dict[str, Any]) -> int:
    beatmap_id = beatmap.get("id")
    if not isinstance(beatmap_id, int):
        msg = "beatmap payload is missing numeric id"
        raise TypeError(msg)
    return beatmap_id


def _has_attributes(attributes: dict[str, Any]) -> bool:
    return isinstance(attributes.get("attributes"), dict)


async def _send_attributes_error(interaction: discord.Interaction, user_id_for_l10n: int) -> None:
    await interaction.followup.send(
        lstr(
            user_id_for_l10n,
            "error_beatmap_attributes_not_found",
            "Could not retrieve beatmap attributes.",
        ),
        ephemeral=True,
    )
