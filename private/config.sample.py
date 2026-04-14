from __future__ import annotations

DISCORD_BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

DEFAULT_LANGUAGE = "en"
DEFAULT_OSU_MODE = (
    0  # 0 for osu!standard, 1 for Taiko, 2 for CatchTheBeat, 3 for osu!mania
)

# 支援的語言列表，對應 locales 文件夾中的文件名 (不含 .json)
SUPPORTED_LANGUAGES = {"en": "English", "zh_TW": "繁體中文"}

# osu! API v2 OAuth Credentials
OSU_API_V2_CLIENT_ID = "YOUR_CLIENT_ID_HERE"  # <--- 請填入您的 Client ID
OSU_API_V2_CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"  # <--- 請填入您的 Client Secret

# osu! API v1 Key (for fallback)
OSU_API_V1_KEY = "YOUR_API_V1_KEY_HERE"  # <--- 請將此處替換為您真實的 API v1 Key
