from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from private import config
from utils import user_data_manager
from utils.localization import get_localized_string as lstr

from .osu_constants import MODE_EMOJI_STRINGS, OSU_MODES_INT_TO_STRING, OSU_MODES_STRING_TO_INT
from .user_errors import UserCommandError
from .user_profile_fields import (
    achievement_text,
    add_standard_profile_fields,
    integer_text,
    join_date_text,
    playstyle_text,
    playtime_text,
    previous_names,
    profile_link_lines,
    profile_status_values,
)
from .user_profile_graph import generate_profile_rank_graph

if TYPE_CHECKING:
    from utils.osu_api import OsuAPI

    from .user_formatting import UserFormatter


TREE_EMOJI = "<:tree:1373314005116125266>"
END_EMOJI = "<:end:1373314035373707445>"
SECTION_EMOJI = "<a:crownlightblue:1374003894346317824>"
SUPPORTER_PROFILE_COLOR = "#e6baff"


@dataclass(frozen=True, kw_only=True)
class ProfileCommandInput:
    osu_user: str | None
    osu_id: int | None
    mode: int | None
    detail: bool


@dataclass(frozen=True, kw_only=True)
class ProfileLookup:
    user_identifier: str
    identifier_type: str
    actual_mode_int: int
    api_mode: str | None


@dataclass(frozen=True, kw_only=True)
class ProfileRenderContext:
    player_data: dict[str, Any]
    mode_stats: dict[str, Any] | None
    user_id_for_l10n: int
    current_mode_int: int
    formatter: UserFormatter


class UserProfileService:
    def __init__(self, osu_api: OsuAPI, formatter: UserFormatter) -> None:
        self.osu_api = osu_api
        self.formatter = formatter

    async def send_profile(
        self, interaction: discord.Interaction, command_input: ProfileCommandInput
    ) -> None:
        user_id_for_l10n = interaction.user.id
        lookup = await self._resolve_lookup(user_id_for_l10n, command_input)
        player_data = await self.osu_api.get_user(
            user_identifier=lookup.user_identifier,
            mode=lookup.api_mode,
            identifier_type=lookup.identifier_type,
        )
        if not player_data:
            await self._send_user_not_found(interaction, lookup)
            return

        mode_int = _resolve_actual_mode(lookup.actual_mode_int, player_data, command_input.mode)
        context = ProfileRenderContext(
            player_data=player_data,
            mode_stats=player_data.get("statistics"),
            user_id_for_l10n=user_id_for_l10n,
            current_mode_int=mode_int,
            formatter=self.formatter,
        )
        embed = _create_profile_embed(context)
        if command_input.detail:
            await self._send_detail_profile(interaction, context, embed=embed)
            return
        add_standard_profile_fields(embed, context)
        await interaction.followup.send(embed=embed)

    async def _resolve_lookup(
        self, user_id_for_l10n: int, command_input: ProfileCommandInput
    ) -> ProfileLookup:
        if command_input.osu_id is not None and command_input.osu_user is not None:
            raise UserCommandError(
                lstr(user_id_for_l10n, "error_only_one_identifier"), ephemeral=True
            )

        identifier, identifier_type = await _resolve_profile_identifier(
            user_id_for_l10n, command_input
        )
        actual_mode_int = (
            command_input.mode if command_input.mode is not None else config.DEFAULT_OSU_MODE
        )
        api_mode = (
            OSU_MODES_INT_TO_STRING.get(actual_mode_int) if command_input.mode is not None else None
        )
        return ProfileLookup(
            user_identifier=identifier,
            identifier_type=identifier_type,
            actual_mode_int=actual_mode_int,
            api_mode=api_mode,
        )

    async def _send_user_not_found(
        self, interaction: discord.Interaction, lookup: ProfileLookup
    ) -> None:
        key = (
            "error_osu_user_id_not_found"
            if lookup.identifier_type == "id"
            else "error_osu_user_not_found"
        )
        await interaction.followup.send(
            self.formatter.lstr_or_na(interaction.user.id, key, lookup.user_identifier)
        )

    async def _send_detail_profile(
        self,
        interaction: discord.Interaction,
        context: ProfileRenderContext,
        *,
        embed: discord.Embed,
    ) -> None:
        graph_buffer, has_rank_graph = generate_profile_rank_graph(
            context.player_data.get("rank_history"), context.user_id_for_l10n
        )
        embed.description = ProfileDetailBuilder(
            context=context, has_rank_graph=has_rank_graph
        ).build()
        if graph_buffer is None:
            await interaction.followup.send(embed=embed)
            return

        embed.set_image(url="attachment://profile_graph.png")
        graph_file = discord.File(graph_buffer, filename="profile_graph.png")
        await interaction.followup.send(embed=embed, files=[graph_file])


@dataclass(frozen=True, kw_only=True)
class ProfileDetailBuilder:
    context: ProfileRenderContext
    has_rank_graph: bool

    def build(self) -> str:
        lines: list[str] = []
        lines.extend(self._mode_lines())
        lines.extend(self._status_lines())
        lines.extend(self._other_lines())
        lines.extend(self._link_lines())
        lines.extend(self._graph_lines())
        return "\n".join(lines)

    def _mode_lines(self) -> list[str]:
        mode_emoji = MODE_EMOJI_STRINGS.get(self.context.current_mode_int, "")
        mode_name = self.context.formatter.mode_name(
            self.context.current_mode_int, self.context.user_id_for_l10n
        )
        label = self.localized("user_profile_game_mode", "Game Mode")
        return [f"**{label}:** {mode_emoji} {mode_name}", ""]

    def _status_lines(self) -> list[str]:
        values = profile_status_values(self.context)
        items = (
            f"**{self.localized('user_profile_global_rank')}:** {values.rank} ({values.country_rank})",
            f"**{self.localized('user_profile_level')}:** {values.level}",
            f"**PP:** {values.pp} {self.localized('user_profile_accuracy')}: {values.accuracy}",
            f"**{self.localized('user_profile_grades')}:** {values.grades}",
            f"**{self.localized('user_profile_accuracy')}:** {values.accuracy}",
            f"**{self.localized('user_profile_play_count')}:** {values.playcount}",
            f"**{self.localized('user_profile_total_score')}:** {values.total_score}",
            f"**{self.localized('user_profile_avg_score', 'Avg. Score')}:** {values.average_score}/{self.localized('user_profile_play_short', 'Play')}",
            f"**{self.localized('user_profile_ranked_score')}:** {values.ranked_score}",
            f"**{self.localized('user_profile_avg_ranked_score', 'Avg. Ranked Score')}:** {values.average_ranked_score}/{self.localized('user_profile_play_short', 'Play')}",
            f"**{self.localized('user_profile_total_hits')}:** {values.total_hits}",
            f"**{self.localized('user_profile_avg_hits', 'Avg. Hits')}:** {values.average_hits}/{self.localized('user_profile_play_short', 'Play')}",
            f"**{self.localized('user_profile_max_combo')}:** {values.max_combo}",
            f"**{self.localized('user_profile_replays_watched')}:** {values.replays}",
        )
        return _section_lines(self.localized("profile_section_status") or "Status", items)

    def _other_lines(self) -> list[str]:
        player_data = self.context.player_data
        formatter = self.context.formatter
        user_id = self.context.user_id_for_l10n
        items = [
            f"**{self.localized('user_profile_previous_names')}:** {previous_names(player_data, formatter, user_id)}",
            f"**{self.localized('user_profile_followers')}:** {integer_text(player_data.get('follower_count'), formatter.na(user_id))}",
            f"**{self.localized('user_profile_playstyle')}:** {playstyle_text(player_data, formatter.na(user_id))}",
            f"**{self.localized('user_profile_achievements')}:** {achievement_text(player_data, formatter.na(user_id))}",
            f"**{self.localized('user_profile_total_playtime')}:** {playtime_text(self.context.mode_stats, formatter.na(user_id))}",
            f"**{self.localized('user_profile_join_date')}:** {join_date_text(player_data.get('join_date'), formatter, user_id)}",
        ]
        return ["", *_section_lines(self.localized("profile_section_other") or "其他", items)]

    def _link_lines(self) -> list[str]:
        link_lines = profile_link_lines(self.context.player_data)
        if not link_lines:
            return []
        return [
            "",
            *_section_lines(f"**{self.localized('user_profile_links')}:**", tuple(link_lines)),
        ]

    def _graph_lines(self) -> list[str]:
        if not self.has_rank_graph:
            return []
        return [f"\n{SECTION_EMOJI} **{self.localized('user_profile_rank_graph')}:**"]

    def localized(self, key: str, *args: object) -> str:
        return self.context.formatter.lstr_or_na(self.context.user_id_for_l10n, key, *args)


async def _resolve_profile_identifier(
    user_id_for_l10n: int, command_input: ProfileCommandInput
) -> tuple[str, str]:
    if command_input.osu_id is not None:
        return str(command_input.osu_id), "id"
    if command_input.osu_user:
        return command_input.osu_user.strip(), "username"

    bound_osu_id = await user_data_manager.get_user_binding(user_id_for_l10n)
    if bound_osu_id:
        return str(bound_osu_id), "id"
    raise UserCommandError(lstr(user_id_for_l10n, "error_osu_user_not_provided_or_bound"))


def _resolve_actual_mode(
    requested_mode_int: int, player_data: dict[str, Any], explicit_mode: int | None
) -> int:
    if explicit_mode is not None or not player_data.get("playmode"):
        return requested_mode_int

    returned_mode = player_data.get("playmode")
    resolved_mode = OSU_MODES_STRING_TO_INT.get(returned_mode)
    if resolved_mode is None:
        logger.warning(
            f"API returned unrecognized playmode: '{returned_mode}'. Keeping mode: {requested_mode_int}"
        )
        return requested_mode_int
    if resolved_mode != requested_mode_int:
        logger.debug(
            "Mode override: user did not specify mode. "
            f"API playmode='{returned_mode}', mode {requested_mode_int} -> {resolved_mode}."
        )
    return resolved_mode


def _create_profile_embed(context: ProfileRenderContext) -> discord.Embed:
    player_data = context.player_data
    user_id = context.user_id_for_l10n
    embed = discord.Embed(
        title=_profile_title(player_data, user_id),
        color=_profile_color(player_data),
        url=_profile_url(player_data),
    )
    if player_data.get("avatar_url"):
        embed.set_thumbnail(url=str(player_data["avatar_url"]))
    return embed


def _profile_title(player_data: dict[str, Any], user_id_for_l10n: int) -> str:
    username = player_data.get("username") or "N/A"
    if not username or username == "N/A":
        return lstr(user_id_for_l10n, "user_profile_title_na", "OSU! Profile")

    english_title = f"{username}'s OSU! Profile"
    localized_template = lstr(user_id_for_l10n, "user_profile_title", english_title)
    if not _is_valid_title_template(localized_template, english_title):
        return english_title
    try:
        return localized_template.format(username)
    except (IndexError, KeyError, ValueError) as exc:
        logger.opt(exception=exc).error(
            f"Formatting localized profile title '{localized_template}' failed."
        )
        return english_title


def _is_valid_title_template(localized_template: str, english_title: str) -> bool:
    return (
        localized_template != english_title
        and "{}" in localized_template
        and "LSTR_KEY_ERROR" not in localized_template
        and "<translation_missing" not in localized_template
    )


def _profile_color(player_data: dict[str, Any]) -> discord.Color:
    group_colour_hex = player_data.get("profile_colour")
    if not group_colour_hex and player_data.get("is_supporter"):
        group_colour_hex = SUPPORTER_PROFILE_COLOR
    if not group_colour_hex:
        return discord.Color.blue()
    try:
        return discord.Color.from_str(group_colour_hex)
    except ValueError:
        logger.warning(f"Could not parse color string: '{group_colour_hex}'.")
        return discord.Color.blue()


def _profile_url(player_data: dict[str, Any]) -> str | None:
    user_id = player_data.get("id")
    if user_id is None:
        return None
    return f"https://osu.ppy.sh/users/{user_id}"


def _section_lines(title: str, items: tuple[str, ...] | list[str]) -> list[str]:
    lines = [f"{SECTION_EMOJI} {title}"]
    for index, item in enumerate(items):
        prefix = END_EMOJI if index == len(items) - 1 else TREE_EMOJI
        lines.append(f"{prefix} {item}")
    return lines
