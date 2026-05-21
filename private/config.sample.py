from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw_value = _env(name)
    return int(raw_value) if raw_value else default


DISCORD_BOT_TOKEN = _env("DISCORD_BOT_TOKEN")

DEFAULT_LANGUAGE = _env("DEFAULT_LANGUAGE", "en")
DEFAULT_OSU_MODE = _env_int("DEFAULT_OSU_MODE", 0)

# 支援的語言列表，對應 locales 文件夾中的文件名 (不含 .json)
SUPPORTED_LANGUAGES = {"en": "English", "zh_TW": "繁體中文"}

# osu! API v2 OAuth Credentials
OSU_API_V2_CLIENT_ID = _env("OSU_API_V2_CLIENT_ID")
OSU_API_V2_CLIENT_SECRET = _env("OSU_API_V2_CLIENT_SECRET")

# osu! API v1 Key (for fallback)
OSU_API_V1_KEY = _env("OSU_API_V1_KEY")
