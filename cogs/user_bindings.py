from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from services.user_bindings import bind_user, get_bound_user, unbind_user
from utils.localization import get_localized_string as lstr

from .command_errors import UserCommandError

if TYPE_CHECKING:
    import discord

    from utils.osu_api import OsuAPI


@dataclass(frozen=True, kw_only=True)
class SetUserCommandInput:
    osu_user: str | None
    osu_id: int | None


@dataclass(frozen=True, kw_only=True)
class BindingTarget:
    identifier: str
    identifier_type: str


class UserBindingService:
    def __init__(self, osu_api: OsuAPI) -> None:
        self.osu_api = osu_api

    async def send_setuser(
        self, interaction: discord.Interaction, command_input: SetUserCommandInput
    ) -> None:
        user_id_for_l10n = interaction.user.id
        target = _binding_target(user_id_for_l10n, command_input)
        if target is None:
            await self._send_current_binding(interaction)
            return

        player_data = await self.osu_api.get_user(
            user_identifier=target.identifier, identifier_type=target.identifier_type
        )
        player_id = _player_id_or_not_found(player_data, target, user_id_for_l10n)
        official_username = _require_username(player_data)
        await bind_user(interaction.user.id, str(player_id))
        await interaction.followup.send(
            lstr(
                user_id_for_l10n,
                "info_setuser_success",
                "Successfully bound osu! account {0}.",
                official_username,
            )
        )

    async def send_unsetuser(self, interaction: discord.Interaction) -> None:
        user_id_for_l10n = interaction.user.id
        removed = await unbind_user(interaction.user.id)
        if removed:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "info_unsetuser_success",
                    "Successfully unbound your osu! account.",
                )
            )
            return

        await interaction.followup.send(
            lstr(
                user_id_for_l10n,
                "error_unsetuser_not_bound",
                "You do not have an osu! account bound to your Discord account.",
            )
        )

    async def _send_current_binding(self, interaction: discord.Interaction) -> None:
        user_id_for_l10n = interaction.user.id
        existing_binding = await get_bound_user(interaction.user.id)
        if not existing_binding:
            await interaction.followup.send(
                lstr(
                    user_id_for_l10n,
                    "info_no_bound_account",
                    "You have not bound any osu! account yet. Use `/setuser <your osu! username or ID>` to bind.",
                )
            )
            return

        player_data = await self.osu_api.get_user(user_identifier=existing_binding)
        await interaction.followup.send(
            lstr(
                user_id_for_l10n,
                "info_your_bound_account",
                "Your currently bound osu! account is: {0}",
                _require_username(player_data),
            )
        )


def _binding_target(
    user_id_for_l10n: int, command_input: SetUserCommandInput
) -> BindingTarget | None:
    if command_input.osu_user and command_input.osu_id:
        raise UserCommandError(
            lstr(
                user_id_for_l10n,
                "error_only_one_identifier",
                "Please provide only one of osu! username or ID, not both.",
            ),
            ephemeral=True,
        )
    if command_input.osu_id:
        return BindingTarget(identifier=str(command_input.osu_id), identifier_type="id")
    if command_input.osu_user:
        return BindingTarget(identifier=command_input.osu_user, identifier_type="username")
    return None


def _player_id_or_not_found(
    player_data: dict[str, Any], target: BindingTarget, user_id_for_l10n: int
) -> Any:
    player_id = player_data.get("id")
    if player_id:
        return player_id

    if target.identifier_type == "id":
        raise UserCommandError(
            lstr(
                user_id_for_l10n,
                "error_osu_user_id_not_found",
                "osu! player id {} not found.",
                target.identifier,
            )
        )

    raise UserCommandError(
        lstr(
            user_id_for_l10n,
            "error_osu_user_not_found",
            "osu! player {} not found.",
            target.identifier,
        )
    )


def _require_username(player_data: dict[str, Any]) -> str:
    username = player_data.get("username")
    if isinstance(username, str) and username:
        return username

    msg = "osu! user payload missing username"
    raise TypeError(msg)
