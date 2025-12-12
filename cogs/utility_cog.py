from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from private import config  # For SUPPORTED_LANGUAGES and DEFAULT_LANGUAGE
from utils.localization import (
    _translations,
    get_user_language,
    set_user_language,
)  # For direct access to translations for language names
from utils.localization import get_localized_string as lstr


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
    if (
        lang_code in predefined_names
        and target_lang_code in predefined_names[lang_code]
    ):
        return predefined_names[lang_code][target_lang_code]
    return lang_code  # Fallback to code


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="lang",
        description="Sets or shows your preferred language for bot responses.",
    )
    @app_commands.describe(
        language_code="The language code to set (e.g., en, zh_TW). Leave empty to see current."
    )
    async def lang(self, interaction: discord.Interaction, language_code: str | None = None) -> None:
        user_id = interaction.user.id
        current_user_lang = get_user_language(user_id)

        available_langs_display = []
        for lc in config.SUPPORTED_LANGUAGES:
            display_name = get_language_display_name(lc, current_user_lang)
            available_langs_display.append(f"{display_name} (`{lc}`)")
        available_langs_str = ", ".join(available_langs_display)

        if language_code is None:
            # Display current language and available languages
            current_lang_display = get_language_display_name(
                current_user_lang, current_user_lang
            )

            # Directly use the translations for the current user's language for this response.
            response_message = "Failed to construct current language message."
            try:
                translations_for_current_lang = _translations.get(current_user_lang, {})
                message_template = translations_for_current_lang.get(
                    "lang_no_code_provided"
                )

                if message_template:
                    response_message = message_template.format(
                        current_lang_display, available_langs_str
                    )
                else:  # Fallback if the template itself is missing
                    default_lang_translations = _translations.get(
                        config.DEFAULT_LANGUAGE, {}
                    )
                    fallback_template = default_lang_translations.get(
                        "lang_no_code_provided"
                    )
                    if fallback_template:
                        response_message = fallback_template.format(
                            current_lang_display, available_langs_str
                        )
                    else:  # Ultimate fallback
                        response_message = f"No language code provided. Current: {current_lang_display}. Available: {available_langs_str}"
            except Exception as e:
                logger.error(
                    f"[UtilityCog] Error formatting lang_no_code_provided: {e}"
                )
                response_message = f"No language code provided. Your current language is **{current_lang_display}**. Available languages: {available_langs_str}"  # Fallback to English structure

            await interaction.response.send_message(response_message, ephemeral=True)
            return

        raw_normalized_code = (
            language_code.strip().lower()
        )  # e.g., "zh_TW" -> "zh_tw", "ZH-TW" -> "zh-tw", "en" -> "en"

        # Standardize to the representation used in SUPPORTED_LANGUAGES
        # config.SUPPORTED_LANGUAGES = ["en", "zh_TW"]
        final_code_to_check = ""
        if raw_normalized_code == "en":
            final_code_to_check = "en"
        elif raw_normalized_code in {
            "zh-tw",
            "zh_tw",
            "zhtw",
        }:  # handles variations like "zh-tw", "zh_tw", "zhtw"
            final_code_to_check = "zh_TW"
        else:
            # For any other code, use it as is for checking against SUPPORTED_LANGUAGES
            final_code_to_check = raw_normalized_code

        # Check if the language code is valid and supported
        if final_code_to_check in config.SUPPORTED_LANGUAGES:
            success = set_user_language(user_id, final_code_to_check)
            if success:
                # Get the display name of the new language IN the new language
                new_lang_display = get_language_display_name(
                    final_code_to_check, final_code_to_check
                )

                # Directly use the translations for the newly set language for this specific response.
                # This ensures the confirmation message itself is in the new language.
                response_message = "Language setting failed to construct message."
                try:
                    translations_for_new_lang = _translations.get(
                        final_code_to_check, {}
                    )
                    message_template = translations_for_new_lang.get("lang_set_success")

                    if message_template:
                        response_message = message_template.format(new_lang_display)
                    else:  # Fallback if the template itself is missing in the new language
                        # Try default language as a secondary fallback for the template
                        default_lang_translations = _translations.get(
                            config.DEFAULT_LANGUAGE, {}
                        )
                        fallback_template = default_lang_translations.get(
                            "lang_set_success"
                        )
                        if fallback_template:
                            response_message = fallback_template.format(
                                new_lang_display
                            )
                        else:  # Ultimate fallback if no template is found anywhere
                            response_message = (
                                f"Language set to: {new_lang_display}"  # Non-localized
                            )
                except Exception as e:
                    logger.error(f"[UtilityCog] Error formatting lang_set_success: {e}")
                    # Fallback to a simple English message if formatting fails
                    response_message = (
                        f"Your language has been set to: **{new_lang_display}**."
                    )

                await interaction.response.send_message(
                    response_message, ephemeral=True
                )
            else:
                # This case should ideally not be reached if final_code_to_check in SUPPORTED_LANGUAGES
                # but set_user_language might have other internal checks in the future.
                await interaction.response.send_message(
                    lstr(user_id, "lang_set_fail", language_code)
                    + "\n"
                    + lstr(user_id, "lang_available_languages", available_langs_str),
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                lstr(user_id, "lang_set_fail", language_code)
                + "\n"
                + lstr(user_id, "lang_available_languages", available_langs_str),
                ephemeral=True,
            )

    # Dynamically generate choices for the language_code parameter
    @lang.autocomplete("language_code")
    async def lang_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        # Get the language for displaying choice names (user\'s current language)
        display_lang_for_choices = get_user_language(interaction.user.id)

        for lang_code_supported in config.SUPPORTED_LANGUAGES:
            display_name = get_language_display_name(
                lang_code_supported, display_lang_for_choices
            )
            if (
                current.lower() in lang_code_supported.lower()
                or current.lower() in display_name.lower()
            ):
                choices.append(
                    app_commands.Choice(
                        name=f"{display_name} ({lang_code_supported})",
                        value=lang_code_supported,
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
