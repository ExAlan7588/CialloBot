from __future__ import annotations

import discord
from discord.ext import commands

from utils.error_handler import handle_interaction_error


class BaseModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        title: str,
        timeout: float | None = None,
    ) -> None:
        super().__init__(title=title, timeout=timeout)
        self.bot = bot

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        await handle_interaction_error(interaction, error, self.bot)
