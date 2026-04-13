from __future__ import annotations

from typing import TYPE_CHECKING

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg


async def get_or_create_guild_config(
    guild_id: int,
    *,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
) -> "asyncpg.Record":
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bread_guild_configs (
                    guild_id,
                    item_name,
                    allow_random_rob,
                    allow_random_give
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id) DO NOTHING
                """,
                guild_id,
                default_item_name,
                default_allow_random_rob,
                default_allow_random_give,
            )

            config_row = await conn.fetchrow(
                """
                SELECT guild_id, item_name, allow_random_rob, allow_random_give
                FROM bread_guild_configs
                WHERE guild_id = $1
                """,
                guild_id,
            )
    except Exception as exc:
        raise DatabaseOperationError(
            "讀取 Bread 群設定失敗。",
            original_exception=exc,
        ) from exc

    if config_row is None:
        raise DatabaseOperationError("找不到 Bread 群設定。")

    return config_row


async def get_or_create_player(
    guild_id: int,
    user_id: int,
    *,
    nickname: str,
) -> "asyncpg.Record":
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bread_players (
                    guild_id,
                    user_id,
                    nickname
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id)
                DO NOTHING
                """,
                guild_id,
                user_id,
                nickname,
            )

            player_row = await conn.fetchrow(
                """
                SELECT
                    guild_id,
                    user_id,
                    nickname,
                    level,
                    xp,
                    item_count,
                    buy_cooldown_until,
                    eat_cooldown_until,
                    rob_cooldown_until,
                    give_cooldown_until,
                    bet_cooldown_until
                FROM bread_players
                WHERE guild_id = $1 AND user_id = $2
                """,
                guild_id,
                user_id,
            )
    except Exception as exc:
        raise DatabaseOperationError(
            "讀取 Bread 玩家資料失敗。",
            original_exception=exc,
        ) from exc

    if player_row is None:
        raise DatabaseOperationError("找不到 Bread 玩家資料。")

    return player_row
