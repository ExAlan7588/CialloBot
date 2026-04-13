from __future__ import annotations

import discord

from utils.response_embeds import WarningEmbed


async def _send_ephemeral_warning(
    interaction: discord.Interaction,
    *,
    author_name: str,
    description: str,
) -> None:
    embed = WarningEmbed(author_name=author_name, description=description)

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except (discord.NotFound, discord.HTTPException):
        return


async def check_global_blacklist(_interaction: discord.Interaction) -> bool:
    return True


async def check_author(
    interaction: discord.Interaction,
    *,
    author_id: int | None,
) -> bool:
    if author_id is None or interaction.user.id == author_id:
        return True

    await _send_ephemeral_warning(
        interaction,
        author_name="無法操作",
        description="只有發起這個互動的使用者可以操作。",
    )
    return False
