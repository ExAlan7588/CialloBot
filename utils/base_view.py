from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands

from utils.error_handler import handle_interaction_error
from utils.interaction_guards import check_author, check_global_blacklist
from utils.misc import capture_exception


class BaseView(discord.ui.View):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        author: discord.User | discord.Member | None,
        timeout: float | None = 600.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author = author
        self.message: discord.Message | None = None
        self.item_states: dict[str, bool] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await check_global_blacklist(interaction):
            return False

        author_id = self.author.id if self.author else None
        return await check_author(interaction, author_id=author_id)

    def stop(self) -> None:
        self.message = None
        super().stop()

    async def on_timeout(self) -> None:
        return

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        _item: discord.ui.Item[Any],
    ) -> None:
        await handle_interaction_error(interaction, error, self.bot)

    @staticmethod
    async def absolute_send(interaction: discord.Interaction, **kwargs: Any) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs)
            else:
                await interaction.response.send_message(**kwargs)
        except discord.NotFound:
            return

    @staticmethod
    async def absolute_edit(interaction: discord.Interaction, **kwargs: Any) -> None:
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(**kwargs)
            else:
                await interaction.response.edit_message(**kwargs)
        except discord.NotFound:
            return
        except discord.HTTPException as exc:
            capture_exception(
                exc,
                context=f"absolute_edit 失敗 (interaction_id={interaction.id})",
                level="warning",
            )
            raise

    def disable_items(self) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                if child.custom_id is not None:
                    self.item_states[child.custom_id] = child.disabled

                if isinstance(child, discord.ui.Button) and child.url:
                    continue

                child.disabled = True

    def enable_items(self) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                if isinstance(child, discord.ui.Button) and child.url:
                    continue

                if child.custom_id is not None:
                    child.disabled = self.item_states.get(child.custom_id, False)
                else:
                    child.disabled = False
