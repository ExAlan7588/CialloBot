from __future__ import annotations

import json
import pathlib
import random

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_user_language  # Import for language preference
from utils.message_tracker import get_message_tracker  # Import for message tracking

COPASTA_FILE = "copypastas.json"
DEFAULT_LANG_KEY = "EN"  # Define a default language key for copypastas


class CopypastaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.copypastas = {}  # This will store { "EN": {"key": "val"}, "zh_TW": ... }
        self.load_copypastas()

    def load_copypastas(self) -> None:
        try:
            if pathlib.Path(COPASTA_FILE).exists():
                with pathlib.Path(COPASTA_FILE).open(encoding="utf-8") as f:
                    loaded_data = json.load(f)
                # Basic validation for the new structure
                if isinstance(loaded_data, dict) and all(
                    isinstance(v, dict) for v in loaded_data.values()
                ):
                    self.copypastas = loaded_data
                    logger.info(
                        f"[CopypastaCog] Successfully loaded {len(self.copypastas)} language categories from {COPASTA_FILE}."
                    )
                    for lang, pastas in self.copypastas.items():
                        logger.info(f"  - Language '{lang}': {len(pastas)} copypastas.")
                else:
                    logger.warning(
                        f"[CopypastaCog] {COPASTA_FILE} does not have the expected structure (dict of dicts). No copypastas loaded."
                    )
                    self.copypastas = {}
            else:
                logger.error(f"[CopypastaCog] {COPASTA_FILE} not found. No copypastas loaded.")
                self.copypastas = {}
        except json.JSONDecodeError:
            logger.error(
                f"[CopypastaCog] Failed to decode {COPASTA_FILE}. Make sure it is valid JSON. No copypastas loaded."
            )
            self.copypastas = {}
        except Exception as e:
            logger.error(
                f"[CopypastaCog] An unexpected error occurred while loading {COPASTA_FILE}: {e}"
            )
            self.copypastas = {}

    @app_commands.command(
        name="copypasta", description="Sends a random copypasta based on your language preference."
    )
    async def send_copypasta(self, interaction: discord.Interaction) -> None:
        if not self.copypastas:
            self.load_copypastas()  # Try reloading
            if not self.copypastas:
                await interaction.response.send_message(
                    "I couldn't find any copypastas to share right now! The collection might be empty or improperly configured.",
                    ephemeral=True,
                )
                return

        user_id = str(interaction.user.id)
        preferred_lang = get_user_language(
            user_id
        )  # e.g., "zh_TW" or "EN" (config.DEFAULT_LANGUAGE)

        # Use the bot's default language from config as the ultimate fallback for copypastas
        # If config.DEFAULT_LANGUAGE is, for example, 'en', we use 'EN' for consistency with our JSON structure.
        # For copypastas, we've used uppercase "EN". Let's ensure consistency.
        # It's better to use a specific default for copypasta source, e.g., "EN".
        copypasta_default_lang_key = DEFAULT_LANG_KEY  # Our "EN"

        pastas_to_choose_from = []

        # 1. Try preferred language
        if self.copypastas.get(preferred_lang):
            pastas_to_choose_from = list(self.copypastas[preferred_lang].values())
            logger.debug(
                f"[CopypastaCog] User {user_id} prefers {preferred_lang}. Found {len(pastas_to_choose_from)} pastas."
            )

        # 2. If preferred language had no pastas (or lang key didn't exist) AND it's not the copypasta default, try copypasta default
        if not pastas_to_choose_from and preferred_lang != copypasta_default_lang_key:
            if self.copypastas.get(copypasta_default_lang_key):
                pastas_to_choose_from = list(self.copypastas[copypasta_default_lang_key].values())
                logger.debug(
                    f"[CopypastaCog] User {user_id} preferred {preferred_lang} (no pastas), falling back to {copypasta_default_lang_key}. Found {len(pastas_to_choose_from)} pastas."
                )
            else:  # Copypasta default language itself has no pastas or key doesn't exist
                logger.debug(
                    f"[CopypastaCog] User {user_id} preferred {preferred_lang} (no pastas). Fallback {copypasta_default_lang_key} also has no pastas or key missing."
                )

        # 3. If still no pastas (e.g., preferred was the default and it was empty, or fallback was also empty)
        if not pastas_to_choose_from:
            # Check if the default key even exists to give a more specific message
            if (
                copypasta_default_lang_key not in self.copypastas
                or not self.copypastas[copypasta_default_lang_key]
            ):
                await interaction.response.send_message(
                    f"Sorry, I don't have any copypastas available, not even in the default language ({copypasta_default_lang_key}).",
                    ephemeral=True,
                )
            else:  # This case means preferred_lang was default_lang_key, and it was empty
                await interaction.response.send_message(
                    f"Sorry, I couldn't find any copypastas for your preferred language ({preferred_lang}) or the default set.",
                    ephemeral=True,
                )
            return

        chosen_copypasta = random.choice(pastas_to_choose_from)
        # Ensure the chosen pasta is not empty (e.g. if "CN1": "" was chosen)
        if not chosen_copypasta.strip():
            await interaction.response.send_message(
                "I picked a copypasta, but it seems to be empty! Please try again, or ask the admin to check the content.",
                ephemeral=True,
            )
            return

        # 發送 copypasta 並追蹤觸發者
        await interaction.response.defer()  # 延遲響應以獲取訊息對象
        sent_message = await interaction.followup.send(chosen_copypasta, wait=True)

        # 記錄訊息和觸發者的映射
        tracker = get_message_tracker()
        tracker.track_message(sent_message.id, interaction.user.id)

        logger.debug(
            f"[CopypastaCog] User {interaction.user.id} triggered copypasta "
            f"(Message ID: {sent_message.id})"
        )


async def setup(bot: commands.Bot) -> None:
    # Ensure LocalizationManager is available if it's set up as part of the bot
    # No explicit action needed here if utils.localization initializes itself and get_user_language is a global func.
    # If it were `bot.localization_manager.get_user_language`, we'd need to ensure bot.localization_manager is set before cog init.
    # But since `get_user_language` is imported directly from the module, it should be fine.
    await bot.add_cog(CopypastaCog(bot))
    logger.info("CopypastaCog loaded with language-aware functionality.")
