from __future__ import annotations

from utils import user_data_manager


async def bind_user(discord_user_id: int, osu_user_id: str) -> bool:
    return await user_data_manager.set_user_binding(discord_user_id, osu_user_id)


async def get_bound_user(discord_user_id: int) -> str | None:
    return await user_data_manager.get_user_binding(discord_user_id)


async def unbind_user(discord_user_id: int) -> bool:
    return await user_data_manager.remove_user_binding(discord_user_id)
