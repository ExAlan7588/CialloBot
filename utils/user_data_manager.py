from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypeAlias

import aiofiles
import aiofiles.os

DATA_FILE = Path("private/user_bindings.json")
DATA_LOCK = asyncio.Lock()
UserBindings: TypeAlias = dict[str, str]


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
    data = json.loads(content)
    if not isinstance(data, dict):
        msg = f"{path} must contain a JSON object"
        raise TypeError(msg)
    return _validate_user_bindings(path, data)


def _validate_user_bindings(path: Path, data: dict[object, object]) -> UserBindings:
    bindings: UserBindings = {}
    for discord_id, osu_user in data.items():
        if not isinstance(discord_id, str) or not discord_id:
            msg = f"{path} contains an invalid Discord user id key: {discord_id!r}"
            raise TypeError(msg)
        if not isinstance(osu_user, str) or not osu_user:
            msg = f"{path} contains an invalid osu! binding for Discord user {discord_id!r}"
            raise TypeError(msg)
        bindings[discord_id] = osu_user
    return bindings


async def save_user_bindings(data: UserBindings) -> None:
    """異步保存使用者綁定數據。"""
    _validate_user_bindings(DATA_FILE, data)
    async with DATA_LOCK, aiofiles.open(DATA_FILE, mode="w", encoding="utf-8") as file:
        await file.write(json.dumps(data, indent=4, ensure_ascii=False))


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
