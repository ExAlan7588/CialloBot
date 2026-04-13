from __future__ import annotations

import builtins
import contextlib
from collections.abc import Iterator, Sequence

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_localized_string as lstr
from utils.localization import get_user_language

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
    "bread profile",
    "bread buy",
    "bread eat",
    "bread give",
    "bread rob",
    "bread bet",
    "bread rank",
    "bread record",
    "bread nickname",
    "bread itemname",
]


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Displays all available slash commands and their descriptions.",
    )
    async def slash_help(self, interaction: discord.Interaction) -> None:
        logger.debug(
            f"[HelpCog] /help command invoked by {interaction.user.name} (ID: {interaction.user.id})"
        )
        user_id_for_l10n = str(interaction.user.id)
        current_lang_code = get_user_language(user_id_for_l10n)
        logger.debug(
            f"[HelpCog] user_id_for_l10n: {user_id_for_l10n}, Detected lang_code for l10n: {current_lang_code}"
        )

        test_title_key = "help_embed_title"
        english_fallback_title = "Available Slash Commands (Fallback)"
        localized_title_test = lstr(
            user_id_for_l10n, test_title_key, english_fallback_title
        )
        logger.debug(
            f"[HelpCog] Attempted lstr for '{test_title_key}': '{localized_title_test}'"
        )

        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e_defer:
            logger.error(f"[HelpCog] Failed to defer interaction for /help: {e_defer}")
            with contextlib.suppress(builtins.BaseException):
                await interaction.followup.send(
                    "Error processing help command (defer failed). Please try again.",
                    ephemeral=True,
                )
            return

        embed_title = localized_title_test
        embed = discord.Embed(title=embed_title, color=discord.Color.blue())

        all_app_commands = self.bot.tree.get_commands()
        logger.debug(f"[HelpCog] Fetched {len(all_app_commands)} app commands.")

        # Sort commands according to DESIRED_COMMAND_ORDER
        def sort_key(cmd_path: str) -> int:
            try:
                return DESIRED_COMMAND_ORDER.index(cmd_path)
            except ValueError:
                return len(DESIRED_COMMAND_ORDER)  # Put commands not in the list at the end

        flattened_commands = list(_flatten_app_commands(all_app_commands))
        sorted_commands = sorted(flattened_commands, key=lambda item: sort_key(item[0]))
        logger.debug(
            f"[HelpCog] Sorted commands: {[cmd_path for cmd_path, _, _ in sorted_commands]}"
        )

        commands_to_display = []
        for i, (cmd_path, cmd_name, cmd_description) in enumerate(sorted_commands):
            logger.debug(
                f"[HelpCog] Processing command {i + 1}/{len(sorted_commands)}: {cmd_path}"
            )
            description_text = cmd_description
            if not description_text or description_text == "...":
                description_text = lstr(
                    user_id_for_l10n,
                    "help_no_description",
                    "No description available.",
                )

            localized_desc_key = f"cmd_desc_{cmd_name.lower().replace(' ', '_')}"
            original_cmd_description = description_text or lstr(
                user_id_for_l10n, "help_no_description", "No description available."
            )
            localized_description = lstr(
                user_id_for_l10n, localized_desc_key, original_cmd_description
            )
            if (
                "<translation_missing" in localized_description
                or localized_description == localized_desc_key
            ):
                localized_description = original_cmd_description

            commands_to_display.append(f"`/{cmd_path}`: {localized_description}")
            logger.debug(
                f"[HelpCog] - Appended full format for {cmd_path}. Current count: {len(commands_to_display)}"
            )

        if commands_to_display:
            embed.description = "\n".join(commands_to_display)
        else:
            embed.description = lstr(
                user_id_for_l10n, "help_no_commands_found", "No slash commands found."
            )

        try:
            await interaction.followup.send(embed=embed)
        except Exception as e_send:
            logger.error(f"[HelpCog] Failed to send help embed: {e_send}")
            # Try to send a simple text message if embed fails
            try:
                fallback_text = (
                    "Could not display help commands as an embed. Please check logs."
                )
                if commands_to_display:
                    fallback_text = "\n".join(commands_to_display)
                await interaction.followup.send(fallback_text, ephemeral=True)
            except Exception:
                logger.exception("[HelpCog] Failed to send plain-text help fallback")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
    logger.info("HelpCog loaded.")


def _flatten_app_commands(
    commands_list: Sequence[
        app_commands.Command | app_commands.Group | app_commands.ContextMenu
    ],
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
