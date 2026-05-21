from __future__ import annotations

import asyncio
from pathlib import Path

import aiofiles
import aiofiles.os

from utils.user_binding_store import (
    UserBindings,
    load_bindings_from_json,
    serialize_user_bindings,
    validate_user_bindings,
)

DATA_FILE = Path("private/user_bindings.json")
DATA_LOCK = asyncio.Lock()


async def load_user_bindings() -> UserBindings:
    """異步加載使用者綁定數據。如果文件不存在，返回空字典。"""
    async with DATA_LOCK:
        if not await aiofiles.os.path.exists(DATA_FILE):
            return {}

        async with aiofiles.open(DATA_FILE, encoding="utf-8") as file:
            content = await file.read()
            if not content:
                msg = f"{DATA_FILE} is empty; expected a JSON object"
                raise ValueError(msg)

            return _load_bindings_from_json(content, DATA_FILE)


def _load_bindings_from_json(content: str, path: Path) -> UserBindings:
    return load_bindings_from_json(content, path)


def _validate_user_bindings(path: Path, data: dict[object, object]) -> UserBindings:
    return validate_user_bindings(path, data)


async def save_user_bindings(data: UserBindings) -> None:
    """異步保存使用者綁定數據。"""
    _validate_user_bindings(DATA_FILE, data)
    async with DATA_LOCK, aiofiles.open(DATA_FILE, mode="w", encoding="utf-8") as file:
        await file.write(serialize_user_bindings(data))


async def set_user_binding(discord_user_id: int, osu_username_or_id: str) -> bool:
    """為指定的 Discord 用戶設置 osu! 綁定。"""
    bindings = await load_user_bindings()
    bindings[str(discord_user_id)] = osu_username_or_id
    await save_user_bindings(bindings)
    return True


async def get_user_binding(discord_user_id: int) -> str | None:
    """獲取指定 Discord 用戶的 osu! 綁定。如果未找到，返回 None。"""
    bindings = await load_user_bindings()
    return bindings.get(str(discord_user_id))


async def remove_user_binding(discord_user_id: int) -> bool:
    """移除指定 Discord 用戶的 osu! 綁定。"""
    bindings = await load_user_bindings()
    if str(discord_user_id) in bindings:
        del bindings[str(discord_user_id)]
        await save_user_bindings(bindings)
        return True
    return False
