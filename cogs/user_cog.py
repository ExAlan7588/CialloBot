from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_localized_string as lstr

from .user_bindings import SetUserCommandInput, UserBindingService
from .user_errors import UserCommandError
from .user_formatting import UserFormatter
from .user_mapper import MapperCommandInput, UserMapperService
from .user_profile import ProfileCommandInput, UserProfileService

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from utils.osu_api import OsuAPI


MODE_CHOICES = [
    app_commands.Choice(name="STD", value=0),
    app_commands.Choice(name="Taiko", value=1),
    app_commands.Choice(name="CTB", value=2),
    app_commands.Choice(name="Mania", value=3),
]
ERROR_DETAIL_LIMIT = 100


class UserCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.osu_api: OsuAPI = bot.osu_api_client
        self.formatter = UserFormatter()
        self.profile_service = UserProfileService(self.osu_api, self.formatter)
        self.mapper_service = UserMapperService(self.osu_api, self.formatter)
        self.binding_service = UserBindingService(self.osu_api)

    @app_commands.command(name="profile", description="Shows a user's osu! profile.")
    @app_commands.describe(
        osu_user="osu! username (optional)",
        osu_id="osu! user ID (optional)",
        mode="Game mode (0:std, 1:taiko, 2:ctb, 3:mania). Defaults to user's or server's default.",
        detail="Show detailed profile info (optional)",
    )
    @app_commands.choices(mode=MODE_CHOICES)
    async def profile(
        self,
        interaction: discord.Interaction,
        *,
        osu_user: str | None = None,
        osu_id: int | None = None,
        mode: app_commands.Choice[int] | None = None,
        detail: bool = False,
    ) -> None:
        await interaction.response.defer()
        command_input = ProfileCommandInput(
            osu_user=osu_user,
            osu_id=osu_id,
            mode=mode.value if mode is not None else None,
            detail=detail,
        )
        await self._run_user_command(
            interaction,
            self.profile_service.send_profile(interaction, command_input),
            command_name="/profile",
        )

    @app_commands.command(name="mapper", description="Shows osu! mapping statistics for a user.")
    @app_commands.describe(osu_user="osu! username (optional)", osu_id="osu! user ID (optional)")
    async def mapper(
        self,
        interaction: discord.Interaction,
        *,
        osu_user: str | None = None,
        osu_id: int | None = None,
    ) -> None:
        await interaction.response.defer()
        command_input = MapperCommandInput(osu_user=osu_user, osu_id=osu_id)
        await self._run_user_command(
            interaction,
            self.mapper_service.send_mapper(interaction, command_input),
            command_name="/mapper",
        )

    @app_commands.command(
        name="setuser", description="Bind your Discord account to your osu! account."
    )
    @app_commands.describe(
        osu_user="Your osu! username (optional)", osu_id="Your osu! user ID (optional)"
    )
    async def setuser(
        self,
        interaction: discord.Interaction,
        *,
        osu_user: str | None = None,
        osu_id: int | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        command_input = SetUserCommandInput(osu_user=osu_user, osu_id=osu_id)
        await self._run_user_command(
            interaction,
            self.binding_service.send_setuser(interaction, command_input),
            command_name="/setuser",
        )

    @app_commands.command(
        name="unsetuser", description="Unbind your Discord account from your osu! account."
    )
    async def unsetuser(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._run_user_command(
            interaction, self.binding_service.send_unsetuser(interaction), command_name="/unsetuser"
        )

    async def _run_user_command(
        self, interaction: discord.Interaction, command_task: Awaitable[None], *, command_name: str
    ) -> None:
        try:
            await command_task
        except UserCommandError as exc:
            await interaction.followup.send(exc.message, ephemeral=exc.ephemeral)
        except Exception as exc:
            await self._send_unexpected_error(interaction, command_name=command_name, exc=exc)

    async def _send_unexpected_error(
        self, interaction: discord.Interaction, *, command_name: str, exc: Exception
    ) -> None:
        logger.opt(exception=exc).error(f"[UserCog] Error in {command_name} command")
        await interaction.followup.send(
            lstr(
                interaction.user.id,
                "error_generic_command",
                "An unexpected error occurred while executing the command: {}",
                _error_detail(exc),
            )
        )


def _error_detail(exc: Exception) -> str:
    detail = str(exc)
    return detail if len(detail) <= ERROR_DETAIL_LIMIT else f"{detail[:ERROR_DETAIL_LIMIT]}..."


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserCog(bot))
    logger.info("UserCog loaded.")
