from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TypeAlias

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from utils.localization import get_user_language
from utils.message_tracker import get_message_tracker

COPASTA_FILE = Path("copypastas.json")
DEFAULT_LANG_KEY = "EN"

Copypastas: TypeAlias = dict[str, dict[str, str]]


class CopypastaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.copypastas: Copypastas = {}
        self.load_copypastas()

    def load_copypastas(self) -> None:
        self.copypastas = _load_copypastas(COPASTA_FILE)
        logger.info(
            f"[CopypastaCog] Successfully loaded {len(self.copypastas)} language categories from {COPASTA_FILE}."
        )
        for lang, pastas in self.copypastas.items():
            logger.info(f"  - Language '{lang}': {len(pastas)} copypastas.")

    @app_commands.command(
        name="copypasta", description="Sends a random copypasta based on your language preference."
    )
    async def send_copypasta(self, interaction: discord.Interaction) -> None:
        if not self.copypastas:
            await interaction.response.send_message(
                "I couldn't find any copypastas to share right now.", ephemeral=True
            )
            return

        preferred_lang = get_user_language(str(interaction.user.id))
        copypasta = self._choose_copypasta(preferred_lang)
        if copypasta is None:
            await self._send_no_copypasta_message(interaction, preferred_lang)
            return
        if not copypasta.strip():
            await interaction.response.send_message(
                "I picked a copypasta, but it seems to be empty! Please try again, or ask the admin to check the content.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        sent_message = await interaction.followup.send(copypasta, wait=True)

        tracker = get_message_tracker()
        tracker.track_message(sent_message.id, interaction.user.id)
        logger.debug(
            f"[CopypastaCog] User {interaction.user.id} triggered copypasta "
            f"(Message ID: {sent_message.id})"
        )

    def _choose_copypasta(self, preferred_lang: str) -> str | None:
        preferred_pastas = self.copypastas.get(preferred_lang)
        if preferred_pastas:
            return random.choice(list(preferred_pastas.values()))

        default_pastas = self.copypastas.get(DEFAULT_LANG_KEY)
        if default_pastas:
            logger.debug(
                f"[CopypastaCog] Falling back from {preferred_lang} to {DEFAULT_LANG_KEY}."
            )
            return random.choice(list(default_pastas.values()))

        return None

    async def _send_no_copypasta_message(
        self, interaction: discord.Interaction, preferred_lang: str
    ) -> None:
        if DEFAULT_LANG_KEY not in self.copypastas or not self.copypastas[DEFAULT_LANG_KEY]:
            message = (
                "Sorry, I don't have any copypastas available, "
                f"not even in the default language ({DEFAULT_LANG_KEY})."
            )
        else:
            message = (
                "Sorry, I couldn't find any copypastas for your preferred language "
                f"({preferred_lang}) or the default set."
            )
        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CopypastaCog(bot))
    logger.info("CopypastaCog loaded with language-aware functionality.")


def _load_copypastas(path: Path) -> Copypastas:
    if not path.exists():
        msg = f"{path} does not exist"
        raise FileNotFoundError(msg)

    loaded_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded_data, dict):
        msg = f"{path} must contain a JSON object"
        raise TypeError(msg)

    return _validate_copypasta_languages(path, loaded_data)


def _validate_copypasta_languages(path: Path, loaded_data: dict[object, object]) -> Copypastas:
    validated: Copypastas = {}
    for lang, pastas in loaded_data.items():
        if not isinstance(lang, str) or not isinstance(pastas, dict):
            msg = f"{path} must contain a mapping of language codes to copypasta objects"
            raise TypeError(msg)
        validated[lang] = _validate_copypasta_entries(path, lang, pastas)
    return validated


def _validate_copypasta_entries(
    path: Path, lang: str, pastas: dict[object, object]
) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in pastas.items():
        if not isinstance(key, str) or not isinstance(value, str):
            msg = f"{path} language {lang} must contain string keys and values"
            raise TypeError(msg)
        validated[key] = value
    return validated
