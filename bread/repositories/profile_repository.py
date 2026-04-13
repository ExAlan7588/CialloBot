from __future__ import annotations

from typing import TYPE_CHECKING, Final

from bread.repositories.shared_state_repository import (
    upsert_and_get_guild_config,
    upsert_and_get_player,
)
from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg

GUILD_CONFIG_READ_ERROR: Final = "讀取 Bread 群設定失敗。"
PLAYER_READ_ERROR: Final = "讀取 Bread 玩家資料失敗。"


async def get_or_create_guild_config(
    guild_id: int,
    *,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
) -> asyncpg.Record:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            config_row = await upsert_and_get_guild_config(
                conn,
                guild_id=guild_id,
                default_item_name=default_item_name,
                default_allow_random_rob=default_allow_random_rob,
                default_allow_random_give=default_allow_random_give,
            )
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(GUILD_CONFIG_READ_ERROR, original_exception=exc) from exc

    return config_row


async def get_or_create_player(guild_id: int, user_id: int, *, nickname: str) -> asyncpg.Record:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            player_row = await upsert_and_get_player(
                conn, guild_id=guild_id, user_id=user_id, nickname=nickname
            )
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(PLAYER_READ_ERROR, original_exception=exc) from exc

    return player_row
