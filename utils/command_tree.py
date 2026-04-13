from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.error_handler import handle_interaction_error
from utils.interaction_guards import check_global_blacklist
from utils.misc import capture_exception


class CustomCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_global_blacklist(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        client = getattr(self, "client", None)

        if isinstance(client, commands.Bot):
            await handle_interaction_error(interaction, error, client)
            return

        capture_exception(error, context="CommandTree 處理失敗")
