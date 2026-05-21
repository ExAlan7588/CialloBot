from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord


class CommandDisplayError(Exception):
    def __init__(self, message: str, *, ephemeral: bool) -> None:
        super().__init__(message)
        self.message = message
        self.ephemeral = ephemeral


class OsuCommandError(CommandDisplayError):
    def __init__(self, message: str, *, ephemeral: bool = True) -> None:
        super().__init__(message, ephemeral=ephemeral)


class PpCommandError(CommandDisplayError):
    def __init__(self, message: str, *, ephemeral: bool = False) -> None:
        super().__init__(message, ephemeral=ephemeral)


class UserCommandError(CommandDisplayError):
    def __init__(self, message: str, *, ephemeral: bool = False) -> None:
        super().__init__(message, ephemeral=ephemeral)


async def send_command_error(
    interaction: discord.Interaction, error: CommandDisplayError
) -> None:
    await interaction.followup.send(error.message, ephemeral=error.ephemeral)
