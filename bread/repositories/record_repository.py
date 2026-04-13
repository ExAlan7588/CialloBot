from __future__ import annotations

from typing import TYPE_CHECKING

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg


async def count_user_records(*, guild_id: int, user_id: int) -> int:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM bread_action_logs
                WHERE guild_id = $1 AND actor_user_id = $2
                """,
                guild_id,
                user_id,
            )
    except Exception as exc:
        raise DatabaseOperationError(
            "計算 Bread 行為紀錄數量失敗。",
            original_exception=exc,
        ) from exc

    return int(total or 0)


async def fetch_user_records_page(
    *,
    guild_id: int,
    user_id: int,
    limit: int,
    offset: int,
) -> list["asyncpg.Record"]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    action_type,
                    delta,
                    result_text,
                    extra_data,
                    created_at
                FROM bread_action_logs
                WHERE guild_id = $1 AND actor_user_id = $2
                ORDER BY created_at DESC, id DESC
                LIMIT $3 OFFSET $4
                """,
                guild_id,
                user_id,
                limit,
                offset,
            )
    except Exception as exc:
        raise DatabaseOperationError(
            "讀取 Bread 行為紀錄失敗。",
            original_exception=exc,
        ) from exc

    return list(rows)
