from __future__ import annotations

from typing import Any

from bread.constants import (
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_ITEM_NAME,
    DEFAULT_LEVEL_BREAD_NUM,
)
from bread.repositories.profile_repository import (
    get_or_create_guild_config,
    get_or_create_player,
)
from utils.exceptions import BusinessError


async def get_profile_data(
    *,
    guild_id: int | None,
    user_id: int,
    nickname: str,
) -> dict[str, Any]:
    if guild_id is None:
        raise BusinessError("Bread 功能目前只能在伺服器內使用。", author_name="無法使用")

    try:
        config_row = await get_or_create_guild_config(
            guild_id,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
        )
        player_row = await get_or_create_player(guild_id, user_id, nickname=nickname)
    except RuntimeError as exc:
        raise BusinessError(
            "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
            author_name="功能未啟用",
        ) from exc

    remaining_to_level = max(DEFAULT_LEVEL_BREAD_NUM - int(player_row["xp"]), 0)

    return {
        "item_name": str(config_row["item_name"]),
        "nickname": str(player_row["nickname"]),
        "level": int(player_row["level"]),
        "xp": int(player_row["xp"]),
        "item_count": int(player_row["item_count"]),
        "remaining_to_level": remaining_to_level,
        "level_target": DEFAULT_LEVEL_BREAD_NUM,
    }
