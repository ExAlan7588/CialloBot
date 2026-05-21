from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            msg = f"Invalid .env line {line_number}: expected KEY=VALUE"
            raise ValueError(msg)

        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), _clean_env_value(value.strip()))


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw_value = _env(name)
    return int(raw_value) if raw_value else default


_load_env_file()

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
