from __future__ import annotations

from typing import TYPE_CHECKING, Final

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg

COUNT_GROUP_PLAYERS_ERROR: Final = "統計群排行榜人數失敗。"
FETCH_GROUP_RANKING_ERROR: Final = "讀取群排行榜失敗。"
COUNT_GLOBAL_PLAYERS_ERROR: Final = "統計全局排行榜人數失敗。"
FETCH_GLOBAL_RANKING_ERROR: Final = "讀取全局排行榜失敗。"


async def count_group_players(guild_id: int) -> int:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COUNT(*) FROM bread_players WHERE guild_id = $1", guild_id
            )
    except Exception as exc:
        raise DatabaseOperationError(COUNT_GROUP_PLAYERS_ERROR, original_exception=exc) from exc

    return int(value or 0)


async def fetch_group_ranking_page(
    guild_id: int, *, limit: int, offset: int
) -> list[asyncpg.Record]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    user_id,
                    nickname,
                    level,
                    xp,
                    item_count
                FROM bread_players
                WHERE guild_id = $1
                ORDER BY level DESC, item_count DESC, user_id ASC
                LIMIT $2 OFFSET $3
                """,
                guild_id,
                limit,
                offset,
            )
    except Exception as exc:
        raise DatabaseOperationError(FETCH_GROUP_RANKING_ERROR, original_exception=exc) from exc

    return list(rows)


async def count_global_players() -> int:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            value = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM bread_players")
    except Exception as exc:
        raise DatabaseOperationError(COUNT_GLOBAL_PLAYERS_ERROR, original_exception=exc) from exc

    return int(value or 0)


async def fetch_global_ranking_page(*, limit: int, offset: int) -> list[asyncpg.Record]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    user_id,
                    MAX(nickname) AS nickname,
                    MAX(level) AS level,
                    SUM(item_count)::BIGINT AS item_count,
                    COUNT(DISTINCT guild_id)::INTEGER AS guild_count
                FROM bread_players
                GROUP BY user_id
                ORDER BY MAX(level) DESC, SUM(item_count) DESC, user_id ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
    except Exception as exc:
        raise DatabaseOperationError(FETCH_GLOBAL_RANKING_ERROR, original_exception=exc) from exc

    return list(rows)
