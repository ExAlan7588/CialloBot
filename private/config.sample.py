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

# PostgreSQL（Bread 系統將優先使用 DATABASE_URL；若未提供，則使用下方 PG_* 組裝）
# 全部留空時，啟動會直接跳過 Bread 資料庫初始化。
DATABASE_URL = None
PG_HOST = None
PG_PORT = 5432
PG_USER = None
PG_PASSWORD = None
PG_DATABASE = None

# PostgreSQL 連線池設定
PG_POOL_MIN_SIZE = 1
PG_POOL_MAX_SIZE = 10
PG_CONNECT_TIMEOUT_SECONDS = 10
