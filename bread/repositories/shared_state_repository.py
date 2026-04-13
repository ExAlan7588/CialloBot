from __future__ import annotations

from typing import TYPE_CHECKING, Final

from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg

MISSING_GUILD_CONFIG_ERROR: Final = "找不到 Bread 群設定。"
MISSING_PLAYER_ERROR: Final = "找不到 Bread 玩家資料。"


async def upsert_and_get_guild_config(
    conn: asyncpg.Connection,
    *,
    guild_id: int,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
) -> asyncpg.Record:
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
    if config_row is None:
        raise DatabaseOperationError(MISSING_GUILD_CONFIG_ERROR)
    return config_row


async def upsert_and_get_player(
    conn: asyncpg.Connection, *, guild_id: int, user_id: int, nickname: str
) -> asyncpg.Record:
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
            bet_cooldown_until,
            updated_at
        FROM bread_players
        WHERE guild_id = $1 AND user_id = $2
        """,
        guild_id,
        user_id,
    )
    if player_row is None:
        raise DatabaseOperationError(MISSING_PLAYER_ERROR)
    return player_row


async def fetch_player(
    conn: asyncpg.Connection, *, guild_id: int, user_id: int
) -> asyncpg.Record | None:
    return await conn.fetchrow(
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
            bet_cooldown_until,
            updated_at
        FROM bread_players
        WHERE guild_id = $1 AND user_id = $2
        """,
        guild_id,
        user_id,
    )


async def count_candidate_players(
    conn: asyncpg.Connection, *, guild_id: int, exclude_user_id: int, min_item_count: int
) -> int:
    total = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM bread_players
        WHERE
            guild_id = $1
            AND user_id <> $2
            AND item_count >= $3
        """,
        guild_id,
        exclude_user_id,
        min_item_count,
    )
    return int(total or 0)


async def fetch_candidate_player_by_offset(
    conn: asyncpg.Connection,
    *,
    guild_id: int,
    exclude_user_id: int,
    min_item_count: int,
    offset: int,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
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
            bet_cooldown_until,
            updated_at
        FROM bread_players
        WHERE
            guild_id = $1
            AND user_id <> $2
            AND item_count >= $3
        ORDER BY user_id ASC
        LIMIT 1 OFFSET $4
        """,
        guild_id,
        exclude_user_id,
        min_item_count,
        offset,
    )
