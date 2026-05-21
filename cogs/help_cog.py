from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_localized_string as lstr
from utils.localization import get_user_language

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# Define the desired order of commands
DESIRED_COMMAND_ORDER = [
    "help",
    "ping",
    "lang",
    "setuser",
    "unsetuser",
    "profile",
    "best",
    "recent",
    "pp",
    "copypasta",
    "mapper",
    "keyword add",
    "keyword list",
]


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="help", description="Displays all available slash commands and their descriptions."
    )
    async def slash_help(self, interaction: discord.Interaction) -> None:
        logger.debug(
            f"[HelpCog] /help command invoked by {interaction.user.name} (ID: {interaction.user.id})"
        )
        user_id_for_l10n = str(interaction.user.id)
        _log_help_language(user_id_for_l10n)
        await interaction.response.defer(ephemeral=True)
        embed = _build_help_embed(self.bot.tree.get_commands(), user_id_for_l10n)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
    logger.info("HelpCog loaded.")


def _flatten_app_commands(
    commands_list: Sequence[app_commands.Command | app_commands.Group | app_commands.ContextMenu],
    *,
    prefix: str = "",
) -> Iterator[tuple[str, str, str]]:
    for cmd in commands_list:
        if isinstance(cmd, app_commands.Group):
            group_prefix = f"{prefix}{cmd.name}".strip()
            yield from _flatten_app_commands(list(cmd.commands), prefix=f"{group_prefix} ")
        elif isinstance(cmd, app_commands.Command):
            full_path = f"{prefix}{cmd.name}".strip()
            yield full_path, full_path, cmd.description


def _log_help_language(user_id_for_l10n: str) -> None:
    current_lang_code = get_user_language(user_id_for_l10n)
    logger.debug(
        f"[HelpCog] user_id_for_l10n: {user_id_for_l10n}, "
        f"Detected lang_code for l10n: {current_lang_code}"
    )


def _build_help_embed(
    commands_list: Sequence[app_commands.Command | app_commands.Group | app_commands.ContextMenu],
    user_id_for_l10n: str,
) -> discord.Embed:
    flattened_commands = list(_flatten_app_commands(commands_list))
    sorted_commands = sorted(flattened_commands, key=lambda item: _command_order(item[0]))
    logger.debug(f"[HelpCog] Sorted commands: {[cmd_path for cmd_path, _, _ in sorted_commands]}")
    command_lines = [
        _command_help_line(index, command, len(sorted_commands), user_id_for_l10n)
        for index, command in enumerate(sorted_commands, start=1)
    ]
    embed = discord.Embed(title=_help_title(user_id_for_l10n), color=discord.Color.blue())
    embed.description = _help_description(command_lines, user_id_for_l10n)
    return embed


def _help_title(user_id_for_l10n: str) -> str:
    title = lstr(user_id_for_l10n, "help_embed_title", "Available Slash Commands")
    logger.debug(f"[HelpCog] Localized help title: '{title}'")
    return title


def _command_order(cmd_path: str) -> int:
    try:
        return DESIRED_COMMAND_ORDER.index(cmd_path)
    except ValueError:
        return len(DESIRED_COMMAND_ORDER)


def _command_help_line(
    index: int, command: tuple[str, str, str], total: int, user_id_for_l10n: str
) -> str:
    cmd_path, cmd_name, cmd_description = command
    logger.debug(f"[HelpCog] Processing command {index}/{total}: {cmd_path}")
    description = _localized_command_description(cmd_name, cmd_description, user_id_for_l10n)
    return f"`/{cmd_path}`: {description}"


def _localized_command_description(
    cmd_name: str, cmd_description: str, user_id_for_l10n: str
) -> str:
    fallback_description = _command_description_fallback(cmd_description, user_id_for_l10n)
    localized_key = f"cmd_desc_{cmd_name.lower().replace(' ', '_')}"
    localized_description = lstr(user_id_for_l10n, localized_key, fallback_description)
    if "<translation_missing" in localized_description or localized_description == localized_key:
        return fallback_description
    return localized_description


def _command_description_fallback(cmd_description: str, user_id_for_l10n: str) -> str:
    if cmd_description and cmd_description != "...":
        return cmd_description
    return lstr(user_id_for_l10n, "help_no_description", "No description available.")


def _help_description(command_lines: list[str], user_id_for_l10n: str) -> str:
    if command_lines:
        return "\n".join(command_lines)
    return lstr(user_id_for_l10n, "help_no_commands_found", "No slash commands found.")
