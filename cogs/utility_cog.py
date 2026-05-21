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


@dataclass(frozen=True)
class LanguageCommandContext:
    user_id: int
    current_language: str
    available_languages: str
    requested_code: str | None
    normalized_code: str | None


def get_language_display_name(lang_code: str, target_lang_code: str) -> str:
    """Tries to get the display name of a language in the target language.
    Falls back to lang_code if no specific display name is found.
    """
    # Example: For 'en', get its name in 'zh_TW' (e.g., "英語")
    # We need a convention for storing language names in locale files, e.g., "lang_name_en", "lang_name_zh_TW"
    # Or, more simply, just display the code or a manually maintained map.
    # For now, let's keep it simple and potentially just show the code or a predefined name.

    # A simple predefined map for display for now (can be expanded or moved to locale files)
    predefined_names = {
        "en": {"en": "English", "zh_TW": "英語"},
        "zh_TW": {"en": "Traditional Chinese", "zh_TW": "繁體中文"},
    }
    if lang_code in predefined_names and target_lang_code in predefined_names[lang_code]:
        return predefined_names[lang_code][target_lang_code]
    return lang_code  # Fallback to code


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

    # Dynamically generate choices for the language_code parameter
    @lang.autocomplete("language_code")
    async def lang_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        # Get the language for displaying choice names (user\'s current language)
        display_lang_for_choices = get_user_language(interaction.user.id)

        for lang_code_supported in config.SUPPORTED_LANGUAGES:
            display_name = get_language_display_name(lang_code_supported, display_lang_for_choices)
            if (
                current.lower() in lang_code_supported.lower()
                or current.lower() in display_name.lower()
            ):
                choices.append(
                    app_commands.Choice(
                        name=f"{display_name} ({lang_code_supported})", value=lang_code_supported
                    )
                )
        return choices[:25]  # Autocomplete can show max 25 choices

    # @app_commands.command(name="help", description="顯示所有可用的指令及其功能。")
    # async def help(self, interaction: discord.Interaction):
    #     user_id = interaction.user.id
    #     embed = discord.Embed(
    #         title=lstr(user_id, "help_title", default="指令列表"),
    #         description=lstr(user_id, "help_description", default="這是我目前支援的指令："),
    #         color=discord.Color.blue()
    #     )
    #
    #     # TODO: Consider making this list dynamic in the future
    #     commands_list = [
    #         {"name": "/help", "value": lstr(user_id, "help_cmd_help", default="顯示此幫助訊息。"), "inline": False},
    #         {"name": "/lang", "value": lstr(user_id, "help_cmd_lang", default="設定或查看機器人回應的語言。"), "inline": False},
    #         {"name": "/recent", "value": lstr(user_id, "help_cmd_recent", default="顯示玩家最近的 osu! 遊玩紀錄。"), "inline": False},
    #         {"name": "/best", "value": lstr(user_id, "help_cmd_best", default="顯示玩家 osu! 的最佳表現。"), "inline": False},
    #         {"name": "/profile", "value": lstr(user_id, "help_cmd_profile", default="顯示玩家的 osu! 個人資料。"), "inline": False},
    #         {"name": "/mapper", "value": lstr(user_id, "help_cmd_mapper", default="顯示玩家的 osu! 做譜統計資料。"), "inline": False},
    #         # Add other commands here as they are implemented
    #     ]
    #
    #     for cmd_info in commands_list:
    #         embed.add_field(name=cmd_info["name"], value=cmd_info["value"], inline=cmd_info["inline"])
    #
    #     embed.set_footer(text=lstr(user_id, "help_footer", default="使用斜線 `/` 來輸入指令。"))
    #
    #     await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
    logger.info("UtilityCog loaded.")


def _normalize_language_code(language_code: str | None) -> str | None:
    if language_code is None:
        return None
    normalized_code = language_code.strip().lower()
    return LANGUAGE_CODE_ALIASES.get(normalized_code, normalized_code)
