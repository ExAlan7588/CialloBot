from __future__ import annotations

import discord


class BaseResponseEmbed(discord.Embed):
    def __init__(
        self,
        *,
        author_name: str,
        description: str = "",
        color: discord.Color,
    ) -> None:
        super().__init__(description=description, color=color)
        self.set_author(name=author_name)


class WarningEmbed(BaseResponseEmbed):
    def __init__(self, *, author_name: str, description: str = "") -> None:
        super().__init__(
            author_name=author_name,
            description=description,
            color=discord.Color.orange(),
        )


class ErrorEmbed(BaseResponseEmbed):
    def __init__(self, *, author_name: str, description: str = "") -> None:
        super().__init__(
            author_name=author_name,
            description=description,
            color=discord.Color.red(),
        )


class SuccessEmbed(BaseResponseEmbed):
    def __init__(self, *, author_name: str, description: str = "") -> None:
        super().__init__(
            author_name=author_name,
            description=description,
            color=discord.Color.green(),
        )
