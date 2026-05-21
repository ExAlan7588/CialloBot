from __future__ import annotations

from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from private import config
from utils.localization import get_language_string, get_user_language, set_user_language
from utils.localization import get_localized_string as lstr

LANGUAGE_CODE_ALIASES = {"en": "en", "zh-tw": "zh_TW", "zh_tw": "zh_TW", "zhtw": "zh_TW"}
LANGUAGE_DISPLAY_NAMES = {
    "en": {"en": "English", "zh_TW": "英語"},
    "zh_TW": {"en": "Traditional Chinese", "zh_TW": "繁體中文"},
}
MAX_AUTOCOMPLETE_CHOICES = 25


@dataclass(frozen=True)
class LanguageCommandContext:
    user_id: int
    current_language: str
    available_languages: str
    requested_code: str | None
    normalized_code: str | None


def get_language_display_name(lang_code: str, target_lang_code: str) -> str:
    return LANGUAGE_DISPLAY_NAMES.get(lang_code, {}).get(target_lang_code, lang_code)


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ping", description="Shows the bot's current Discord gateway latency."
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        gateway_latency_ms = round(self.bot.latency * 1000)

        # 简体注释：这里只展示 Discord gateway 心跳延迟，不是完整 HTTP 往返时间。
        await interaction.response.send_message(
            lstr(
                user_id,
                "ping_response_gateway",
                "🏓 Discord gateway latency: **{gateway_ms} ms**",
                gateway_ms=gateway_latency_ms,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="lang", description="Sets or shows your preferred language for bot responses."
    )
    @app_commands.describe(
        language_code="The language code to set (e.g., en, zh_TW). Leave empty to see current."
    )
    async def lang(
        self, interaction: discord.Interaction, language_code: str | None = None
    ) -> None:
        context = self._language_context(interaction.user.id, language_code)
        if context.requested_code is None:
            await self._send_current_language(interaction, context)
            return

        if context.normalized_code not in config.SUPPORTED_LANGUAGES:
            await self._send_language_error(interaction, context)
            return

        if not set_user_language(context.user_id, context.normalized_code):
            await self._send_language_error(interaction, context)
            return

        await self._send_language_success(interaction, context)

    def _language_context(self, user_id: int, requested_code: str | None) -> LanguageCommandContext:
        current_language = get_user_language(user_id)
        return LanguageCommandContext(
            user_id=user_id,
            current_language=current_language,
            available_languages=self._available_languages(current_language),
            requested_code=requested_code,
            normalized_code=_normalize_language_code(requested_code),
        )

    def _available_languages(self, target_lang_code: str) -> str:
        return ", ".join(
            f"{get_language_display_name(lang_code, target_lang_code)} (`{lang_code}`)"
            for lang_code in config.SUPPORTED_LANGUAGES
        )

    async def _send_current_language(
        self, interaction: discord.Interaction, context: LanguageCommandContext
    ) -> None:
        current_lang_display = get_language_display_name(
            context.current_language, context.current_language
        )
        response_message = get_language_string(
            context.current_language,
            "lang_no_code_provided",
            "No language code provided. Your current language is **{}**. Available languages: {}",
            current_lang_display,
            context.available_languages,
        )
        await interaction.response.send_message(response_message, ephemeral=True)

    async def _send_language_success(
        self, interaction: discord.Interaction, context: LanguageCommandContext
    ) -> None:
        if context.normalized_code is None:
            msg = "normalized language code is required for success response"
            raise ValueError(msg)

        new_lang_display = get_language_display_name(
            context.normalized_code, context.normalized_code
        )
        response_message = get_language_string(
            context.normalized_code,
            "lang_set_success",
            "Your language has been set to: **{}**.",
            new_lang_display,
        )
        await interaction.response.send_message(response_message, ephemeral=True)

    async def _send_language_error(
        self, interaction: discord.Interaction, context: LanguageCommandContext
    ) -> None:
        response_message = (
            lstr(context.user_id, "lang_set_fail", context.requested_code)
            + "\n"
            + lstr(context.user_id, "lang_available_languages", context.available_languages)
        )
        await interaction.response.send_message(response_message, ephemeral=True)

    @lang.autocomplete("language_code")
    async def lang_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        current_lower = current.lower()
        display_lang_for_choices = get_user_language(interaction.user.id)

        for lang_code_supported in config.SUPPORTED_LANGUAGES:
            display_name = get_language_display_name(lang_code_supported, display_lang_for_choices)
            if (
                current_lower in lang_code_supported.lower()
                or current_lower in display_name.lower()
            ):
                choices.append(
                    app_commands.Choice(
                        name=f"{display_name} ({lang_code_supported})", value=lang_code_supported
                    )
                )
                if len(choices) == MAX_AUTOCOMPLETE_CHOICES:
                    break
        return choices


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
    logger.info("UtilityCog loaded.")


def _normalize_language_code(language_code: str | None) -> str | None:
    if language_code is None:
        return None
    normalized_code = language_code.strip().lower()
    return LANGUAGE_CODE_ALIASES.get(normalized_code, normalized_code)
