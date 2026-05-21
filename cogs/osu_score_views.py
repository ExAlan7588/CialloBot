from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Protocol

import discord
from loguru import logger

from utils.localization import get_localized_string as lstr

from .osu_constants import BP_RANK_INPUT_MAX_LENGTH, SCORE_VIEW_TIMEOUT_SECONDS
from .osu_score_embeds import ScoreEmbedRequest


class ScoreEmbedFactory(Protocol):
    async def create(self, request: ScoreEmbedRequest) -> discord.Embed:
        """Create an embed for one osu! score."""
        ...


@dataclass(frozen=True, kw_only=True)
class ScoreViewConfig:
    embed_factory: ScoreEmbedFactory
    scores: list[dict[str, Any]]
    osu_player_name: str
    player_avatar_url: str | None
    mode_int: int
    user_id_for_l10n: int
    timeout: float = SCORE_VIEW_TIMEOUT_SECONDS


class PreviousBestButton(discord.ui.Button):
    def __init__(self, user_id_for_l10n: int) -> None:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_previous_bp", "Previous BP"),
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, BestScoreView) or view.current_index == 0:
            await interaction.response.defer()
            return

        view.current_index -= 1
        await view.update_embed(interaction)


class NextBestButton(discord.ui.Button):
    def __init__(self, user_id_for_l10n: int) -> None:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_next_bp", "Next BP"),
            style=discord.ButtonStyle.secondary,
            emoji="➡️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, BestScoreView) or view.current_index >= len(view.scores_list) - 1:
            await interaction.response.defer()
            return

        view.current_index += 1
        await view.update_embed(interaction)


class JumpToBPModal(discord.ui.Modal):
    def __init__(self, view: BestScoreView, user_id_for_l10n: int) -> None:
        super().__init__(
            title=lstr(user_id_for_l10n, "modal_jump_to_bp_title", "Jump to Specific BP")
        )
        self.parent_view = view
        self.user_id_for_l10n = user_id_for_l10n
        self.bp_rank_input = discord.ui.TextInput(
            label=lstr(
                user_id_for_l10n,
                "modal_bp_rank_label",
                "BP Rank (1-{max_bp})",
                max_bp=len(self.parent_view.scores_list) if self.parent_view.scores_list else 200,
            ),
            placeholder=lstr(user_id_for_l10n, "modal_bp_rank_placeholder", "Enter a number"),
            min_length=1,
            max_length=BP_RANK_INPUT_MAX_LENGTH,
        )
        self.add_item(self.bp_rank_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rank_to_jump = int(self.bp_rank_input.value)
        except ValueError:
            await self._send_invalid_format(interaction)
            return

        if not 1 <= rank_to_jump <= len(self.parent_view.scores_list):
            await self._send_invalid_range(interaction)
            return

        self.parent_view.current_index = rank_to_jump - 1
        await self.parent_view.update_embed(interaction)

    async def _send_invalid_format(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            lstr(self.user_id_for_l10n, "error_invalid_bp_rank_format", "請輸入有效的數字BP排名。"),
            ephemeral=True,
        )

    async def _send_invalid_range(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            lstr(
                self.user_id_for_l10n, "error_invalid_bp_rank_range", "輸入的BP排名無效或超出範圍。"
            ),
            ephemeral=True,
        )


class JumpToBPButton(discord.ui.Button):
    def __init__(self, user_id_for_l10n: int) -> None:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_jump_to_bp", "Jump"),
            style=discord.ButtonStyle.secondary,
            emoji="\u23f9",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, BestScoreView) or not view.scores_list:
            await interaction.response.defer()
            return

        await interaction.response.send_modal(
            JumpToBPModal(view=view, user_id_for_l10n=view.config.user_id_for_l10n)
        )


class BestScoreView(discord.ui.View):
    def __init__(self, config: ScoreViewConfig) -> None:
        super().__init__(timeout=config.timeout)
        self.config = config
        self.scores_list = config.scores
        self.current_index = 0
        self.message: discord.Message | None = None
        logger.debug(
            f"[BestScoreView __init__] Initialized with {len(self.scores_list)} scores "
            f"for player {config.osu_player_name}."
        )

        self.prev_button = PreviousBestButton(user_id_for_l10n=config.user_id_for_l10n)
        self.jump_button = JumpToBPButton(user_id_for_l10n=config.user_id_for_l10n)
        self.next_button = NextBestButton(user_id_for_l10n=config.user_id_for_l10n)
        self.add_item(self.prev_button)
        self.add_item(self.jump_button)
        self.add_item(self.next_button)
        self._update_button_states()

    def _update_button_states(self) -> None:
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.scores_list) - 1
        self.jump_button.disabled = not self.scores_list

    async def update_embed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self.config.embed_factory.create(
            _build_embed_request(
                self.config, self.scores_list[self.current_index], self.current_index + 1
            )
        )
        self._update_button_states()
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self) -> None:
        await _disable_timed_out_view(self)


class PreviousRecentButton(discord.ui.Button):
    def __init__(self, user_id_for_l10n: int) -> None:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_previous_recent", "Previous Play"),
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, RecentScoreView) or view.current_index == 0:
            await interaction.response.defer()
            return

        view.current_index -= 1
        await view.update_embed(interaction)


class NextRecentButton(discord.ui.Button):
    def __init__(self, user_id_for_l10n: int) -> None:
        super().__init__(
            label=lstr(user_id_for_l10n, "button_next_recent", "Next Play"),
            style=discord.ButtonStyle.secondary,
            emoji="➡️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, RecentScoreView) or view.current_index >= len(view.scores_list) - 1:
            await interaction.response.defer()
            return

        view.current_index += 1
        await view.update_embed(interaction)


class RecentScoreView(discord.ui.View):
    def __init__(self, config: ScoreViewConfig) -> None:
        super().__init__(timeout=config.timeout)
        self.config = config
        self.scores_list = config.scores
        self.current_index = 0
        self.message: discord.Message | None = None
        self.prev_button = PreviousRecentButton(user_id_for_l10n=config.user_id_for_l10n)
        self.next_button = NextRecentButton(user_id_for_l10n=config.user_id_for_l10n)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self._update_button_states()

    def _update_button_states(self) -> None:
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.scores_list) - 1

    async def update_embed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self.config.embed_factory.create(
            _build_embed_request(self.config, self.scores_list[self.current_index], None)
        )
        self._update_button_states()
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self) -> None:
        await _disable_timed_out_view(self)


def _build_embed_request(
    config: ScoreViewConfig, score_data: dict[str, Any], rank_in_top: int | None
) -> ScoreEmbedRequest:
    return ScoreEmbedRequest(
        score_data=score_data,
        player_name=config.osu_player_name,
        player_avatar_url=config.player_avatar_url,
        mode_int=config.mode_int,
        user_id_for_l10n=config.user_id_for_l10n,
        rank_in_top=rank_in_top,
    )


async def _disable_timed_out_view(view: BestScoreView | RecentScoreView) -> None:
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.disabled = True
    if view.message is not None:
        with contextlib.suppress(discord.NotFound):
            await view.message.edit(view=view)
