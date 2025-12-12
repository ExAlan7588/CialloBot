from __future__ import annotations

import asyncio
import json
import pathlib

import aiofiles
from loguru import logger

DATA_FILE = "private/user_bindings.json"
DATA_LOCK = asyncio.Lock()


async def load_user_bindings():
    """異步加載使用者綁定數據。如果文件不存在，返回空字典。"""
    async with DATA_LOCK:
        if not pathlib.Path(DATA_FILE).exists():
            return {}
        try:
            async with aiofiles.open(DATA_FILE, encoding="utf-8") as f:
                content = await f.read()
                if not content:  # 文件是空的
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            # 文件內容不是有效的 JSON，可能已損壞
            # 可以考慮在這裡記錄錯誤或創建一個備份
            return {}
        except Exception as e:
            # 其他可能的錯誤
            logger.error(f"Error loading user bindings: {e}")
            return {}


async def save_user_bindings(data) -> None:
    """異步保存使用者綁定數據。"""
    async with DATA_LOCK:
        try:
            async with aiofiles.open(DATA_FILE, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=4, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Error saving user bindings: {e}")


async def set_user_binding(discord_user_id: int, osu_username_or_id: str) -> bool:
    """為指定的 Discord 用戶設置 osu! 綁定。"""
    bindings = await load_user_bindings()
    bindings[str(discord_user_id)] = osu_username_or_id
    await save_user_bindings(bindings)
    return True


async def get_user_binding(discord_user_id: int):
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
