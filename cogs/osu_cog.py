from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from private import config
from services.user_bindings import get_bound_user
from utils.localization import get_language_string, get_user_language
from utils.localization import get_localized_string as lstr

from .command_errors import OsuCommandError, send_command_error
from .osu_constants import (
    BEST_SCORE_LIMIT,
    ERROR_DETAIL_LIMIT,
    OSU_MODES_INT_TO_STRING,
    OSU_MODES_STRING_TO_INT,
    RECENT_SCORE_LIMIT,
)
from .osu_formatting import get_osu_mode_name
from .osu_score_embeds import ScoreEmbedBuilder, ScoreEmbedRequest
from .osu_score_views import BestScoreView, RecentScoreView, ScoreViewConfig

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI


MODE_CHOICES = [
    app_commands.Choice(name="STD", value=0),
    app_commands.Choice(name="Taiko", value=1),
    app_commands.Choice(name="CTB", value=2),
    app_commands.Choice(name="Mania", value=3),
]


@dataclass(frozen=True, kw_only=True)
class PlayerCommandContext:
    user_identifier: str
    user_id_for_l10n: int
    player_data: dict[str, Any]
    numeric_user_id: int | str
    player_name: str
    player_avatar_url: str | None
    mode_int: int
    mode_str: str


@dataclass(frozen=True, kw_only=True)
class RecentCommandInput:
    osu_user: str | None
    osu_id: int | None
    mode: int | None


@dataclass(frozen=True, kw_only=True)
class BestCommandInput:
    osu_user: str | None
    mode: int | None
    bp_rank: int | None


@dataclass(frozen=True, kw_only=True)
class PlayerLookupRequest:
    user_identifier: str
    player_data: dict[str, Any]
    requested_mode: int | None
    user_id_for_l10n: int
    command_name: str


class OsuCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client
        self.score_embed_builder = ScoreEmbedBuilder(
            osu_api=self.osu_api,
            mode_name_resolver=self.get_mode_name,
            na_value_resolver=self.get_na_value,
        )

    def get_na_value(self, user_id_for_l10n: int) -> str:
        current_lang = get_user_language(str(user_id_for_l10n))
        return get_language_string(current_lang, "value_not_available", "N/A")

    def get_mode_name(
        self, mode_int: int, user_id_for_l10n: int, *, name_only: bool = False
    ) -> str:
        return get_osu_mode_name(
            mode_int, user_id_for_l10n, name_only=name_only, log_prefix="OSU_COG"
        )

    @app_commands.command(name="recent", description="Shows the most recent osu! score for a user.")
    @app_commands.describe(
        osu_user="osu! username (optional)",
        osu_id="osu! user ID (optional)",
        mode="Game mode. Defaults to user's or server's default.",
    )
    @app_commands.choices(mode=MODE_CHOICES)
    async def recent(
        self,
        interaction: discord.Interaction,
        *,
        osu_user: str | None = None,
        osu_id: int | None = None,
        mode: int | None = None,
    ) -> None:
        user_id_for_l10n = interaction.user.id
        await interaction.response.defer()
        command_input = RecentCommandInput(osu_user=osu_user, osu_id=osu_id, mode=mode)
        try:
            await self._send_recent_score(interaction, command_input)
        except OsuCommandError as exc:
            await send_command_error(interaction, exc)
        except Exception as exc:
            await self._send_unexpected_error(
                interaction, user_id_for_l10n, command_name="/recent", exc=exc
            )

    @app_commands.command(name="best", description="Shows a user's top osu! score.")
    @app_commands.describe(
        osu_user="osu! username or ID",
        mode="Game mode. Defaults to user's or server's default.",
        bp_rank="BP rank to display (1-200, optional)",
    )
    @app_commands.choices(mode=MODE_CHOICES)
    async def best(
        self,
        interaction: discord.Interaction,
        *,
        osu_user: str | None = None,
        mode: int | None = None,
        bp_rank: int | None = None,
    ) -> None:
        user_id_for_l10n = interaction.user.id
        await interaction.response.defer()
        command_input = BestCommandInput(osu_user=osu_user, mode=mode, bp_rank=bp_rank)
        try:
            await self._send_best_score(interaction, command_input)
        except OsuCommandError as exc:
            await send_command_error(interaction, exc)
        except Exception as exc:
            await self._send_unexpected_error(
                interaction, user_id_for_l10n, command_name="/best", exc=exc
            )

    async def _send_recent_score(
        self, interaction: discord.Interaction, command_input: RecentCommandInput
    ) -> None:
        logger.debug(
            f"[OSU_COG /recent] CMD_INVOKED: osu_user='{command_input.osu_user}', "
            f"osu_id='{command_input.osu_id}', mode={command_input.mode}"
        )
        context = await self._resolve_recent_context(interaction.user.id, command_input)
        recent_scores = await self._fetch_recent_scores(context)
        embed = await self._create_score_embed(
            _score_embed_request(context, recent_scores[0], None)
        )
        view = self._recent_view(context, recent_scores)
        view.message = await interaction.followup.send(embed=embed, view=view)

    async def _send_best_score(
        self, interaction: discord.Interaction, command_input: BestCommandInput
    ) -> None:
        context = await self._resolve_best_context(interaction.user.id, command_input)
        best_scores = await self._fetch_best_scores(context)
        initial_index = _resolve_best_index(command_input, best_scores, context)
        embed = await self._create_score_embed(
            _score_embed_request(context, best_scores[initial_index], initial_index + 1)
        )
        view = self._best_view(context, best_scores, initial_index=initial_index)
        view.message = await interaction.followup.send(embed=embed, view=view)

    async def _resolve_recent_context(
        self, user_id_for_l10n: int, command_input: RecentCommandInput
    ) -> PlayerCommandContext:
        user_identifier = await self._resolve_recent_user_identifier(
            user_id_for_l10n, command_input
        )
        return await self._build_player_context(
            PlayerLookupRequest(
                user_identifier=user_identifier,
                player_data={},
                requested_mode=command_input.mode,
                user_id_for_l10n=user_id_for_l10n,
                command_name="recent",
            )
        )

    async def _resolve_best_context(
        self, user_id_for_l10n: int, command_input: BestCommandInput
    ) -> PlayerCommandContext:
        user_identifier = await self._resolve_best_user_identifier(user_id_for_l10n, command_input)
        return await self._build_player_context(
            PlayerLookupRequest(
                user_identifier=user_identifier,
                player_data={},
                requested_mode=command_input.mode,
                user_id_for_l10n=user_id_for_l10n,
                command_name="best",
            )
        )

    async def _resolve_recent_user_identifier(
        self, user_id_for_l10n: int, command_input: RecentCommandInput
    ) -> str:
        if command_input.osu_id is not None:
            return str(command_input.osu_id)
        if command_input.osu_user and command_input.osu_user.strip():
            return command_input.osu_user.strip()
        return await _bound_user_or_error(user_id_for_l10n)

    async def _resolve_best_user_identifier(
        self, user_id_for_l10n: int, command_input: BestCommandInput
    ) -> str:
        if command_input.osu_user and command_input.osu_user.strip():
            return command_input.osu_user.strip()
        return await _bound_user_or_error(user_id_for_l10n)

    async def _build_player_context(self, request: PlayerLookupRequest) -> PlayerCommandContext:
        logger.debug(
            f"[OSU_COG _build_player_context] Attempting to get user: {request.user_identifier}"
        )
        player_data = await self.osu_api.get_user(user_identifier=request.user_identifier)
        if not player_data:
            raise OsuCommandError(
                lstr(
                    request.user_id_for_l10n,
                    "error_user_not_found",
                    "Player **{}** not found.",
                    request.user_identifier,
                )
            )

        context_request = PlayerLookupRequest(
            user_identifier=request.user_identifier,
            player_data=player_data,
            requested_mode=request.requested_mode,
            user_id_for_l10n=request.user_id_for_l10n,
            command_name=request.command_name,
        )
        mode_int = self._determine_game_mode(context_request)
        mode_str = _resolve_mode_string(mode_int, request.command_name)
        return PlayerCommandContext(
            user_identifier=request.user_identifier,
            user_id_for_l10n=request.user_id_for_l10n,
            player_data=player_data,
            numeric_user_id=_require_player_id(player_data, request.user_identifier),
            player_name=str(player_data.get("username") or request.user_identifier),
            player_avatar_url=player_data.get("avatar_url"),
            mode_int=mode_int,
            mode_str=mode_str,
        )

    def _determine_game_mode(self, request: PlayerLookupRequest) -> int:
        if request.requested_mode is not None:
            logger.debug(
                f"[OSU_COG /{request.command_name}] User provided mode: {request.requested_mode}"
            )
            return request.requested_mode

        player_playmode = request.player_data.get("playmode")
        if player_playmode in OSU_MODES_STRING_TO_INT:
            mode_int = OSU_MODES_STRING_TO_INT[player_playmode]
            logger.debug(
                f"[OSU_COG /{request.command_name}] Using user API default mode: "
                f"{player_playmode} -> {mode_int}"
            )
            return mode_int

        if player_playmode:
            logger.debug(
                f"[OSU_COG /{request.command_name}] User API default mode "
                f"'{player_playmode}' not recognized, using config default: {config.DEFAULT_OSU_MODE}"
            )
        return config.DEFAULT_OSU_MODE

    async def _fetch_recent_scores(self, context: PlayerCommandContext) -> list[dict[str, Any]]:
        logger.debug(
            f"[OSU_COG DEBUG /recent] Fetching recent plays for user ID: "
            f"{context.numeric_user_id}, mode: {context.mode_str}"
        )
        scores = await self.osu_api.get_user_recent(
            user_id=str(context.numeric_user_id),
            mode=context.mode_str,
            limit=RECENT_SCORE_LIMIT,
            include_fails=True,
        )
        score_dicts = _expect_score_dicts(scores, "recent")
        if not score_dicts:
            raise OsuCommandError(
                lstr(
                    context.user_id_for_l10n,
                    "error_no_recent_plays",
                    "No recent plays found for **{}** in the selected mode.",
                    context.player_name,
                )
            )
        _log_score_batch("recent", score_dicts, context)
        return score_dicts

    async def _fetch_best_scores(self, context: PlayerCommandContext) -> list[dict[str, Any]]:
        scores = await self.osu_api.get_user_best(
            user_id=str(context.numeric_user_id), mode=context.mode_str, limit=BEST_SCORE_LIMIT
        )
        score_dicts = _expect_score_dicts(scores, "best")
        if not score_dicts:
            logger.debug(
                f"[OSU_COG /best] No best plays found for user {context.player_name} "
                f"(ID: {context.numeric_user_id}) in mode {context.mode_str}."
            )
            raise OsuCommandError(
                lstr(
                    context.user_id_for_l10n,
                    "error_no_best_plays",
                    "No best plays found for player **{}** in the selected mode or they have no plays.",
                    context.player_name,
                )
            )
        _log_score_batch("best", score_dicts, context)
        return score_dicts

    async def _create_score_embed(self, request: ScoreEmbedRequest) -> discord.Embed:
        return await self.score_embed_builder.create(request)

    def _recent_view(
        self, context: PlayerCommandContext, scores: list[dict[str, Any]]
    ) -> RecentScoreView:
        return RecentScoreView(_score_view_config(self.score_embed_builder, context, scores))

    def _best_view(
        self, context: PlayerCommandContext, scores: list[dict[str, Any]], *, initial_index: int
    ) -> BestScoreView:
        view = BestScoreView(_score_view_config(self.score_embed_builder, context, scores))
        view.current_index = initial_index
        view._update_button_states()
        return view

    async def _send_unexpected_error(
        self,
        interaction: discord.Interaction,
        user_id_for_l10n: int,
        *,
        command_name: str,
        exc: Exception,
    ) -> None:
        logger.opt(exception=exc).error(f"[OSU_COG ERROR {command_name}] Error in command")
        await interaction.followup.send(
            lstr(
                user_id_for_l10n,
                "error_generic_command",
                "An unexpected error occurred while executing the command: {}",
                _error_detail(exc),
            ),
            ephemeral=True,
        )


async def _bound_user_or_error(user_id_for_l10n: int) -> str:
    bound_osu_user = await get_bound_user(user_id_for_l10n)
    if bound_osu_user:
        return str(bound_osu_user)

    raise OsuCommandError(
        lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound"), ephemeral=False
    )


def _resolve_mode_string(mode_int: int, command_name: str) -> str:
    mode_str = OSU_MODES_INT_TO_STRING.get(mode_int)
    if mode_str is None:
        msg = f"[OSU_COG ERROR /{command_name}] Invalid game mode resolved: {mode_int}"
        raise RuntimeError(msg)
    logger.debug(f"[OSU_COG DEBUG /{command_name}] MODE_RESOLVE_SUCCESS: '{mode_str}'")
    return mode_str


def _require_player_id(player_data: dict[str, Any], user_identifier: str) -> int | str:
    player_id = player_data.get("id")
    if player_id is None:
        msg = f"osu! user payload for '{user_identifier}' is missing id"
        raise RuntimeError(msg)
    return player_id


def _expect_score_dicts(scores: list[Any], command_name: str) -> list[dict[str, Any]]:
    invalid_indexes = [index for index, score in enumerate(scores) if not isinstance(score, dict)]
    if invalid_indexes:
        msg = (
            f"osu! {command_name} scores contained non-object entries at indexes {invalid_indexes}"
        )
        raise TypeError(msg)
    return list(scores)


def _log_score_batch(
    command_name: str, scores: list[dict[str, Any]], context: PlayerCommandContext
) -> None:
    logger.debug(
        f"[OSU_COG /{command_name}] Fetched {len(scores)} scores for user "
        f"{context.player_name} in mode {context.mode_str}."
    )
    logger.debug(
        f"[OSU_COG /{command_name}] First score data (mode: {context.mode_str}): "
        f"{str(scores[0])[:500]}..."
    )


def _resolve_best_index(
    command_input: BestCommandInput,
    best_scores: list[dict[str, Any]],
    context: PlayerCommandContext,
) -> int:
    if command_input.bp_rank is None:
        return 0
    if 1 <= command_input.bp_rank <= len(best_scores):
        return command_input.bp_rank - 1

    raise OsuCommandError(
        lstr(
            context.user_id_for_l10n,
            "error_best_play_not_found",
            "Best play #{} not found for player {}.",
            command_input.bp_rank,
            context.player_name,
        )
    )


def _score_embed_request(
    context: PlayerCommandContext, score_data: dict[str, Any], rank_in_top: int | None
) -> ScoreEmbedRequest:
    return ScoreEmbedRequest(
        score_data=score_data,
        player_name=context.player_name,
        player_avatar_url=context.player_avatar_url,
        mode_int=context.mode_int,
        user_id_for_l10n=context.user_id_for_l10n,
        rank_in_top=rank_in_top,
    )


def _score_view_config(
    embed_factory: ScoreEmbedBuilder, context: PlayerCommandContext, scores: list[dict[str, Any]]
) -> ScoreViewConfig:
    return ScoreViewConfig(
        embed_factory=embed_factory,
        scores=scores,
        osu_player_name=context.player_name,
        player_avatar_url=context.player_avatar_url,
        mode_int=context.mode_int,
        user_id_for_l10n=context.user_id_for_l10n,
    )


def _error_detail(exc: Exception) -> str:
    detail = str(exc)
    return detail if len(detail) <= ERROR_DETAIL_LIMIT else f"{detail[:ERROR_DETAIL_LIMIT]}..."


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OsuCog(bot))
    logger.info("OsuCog loaded.")
