from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

if TYPE_CHECKING:
    import asyncpg


async def get_or_create_buy_context(
    *,
    guild_id: int,
    user_id: int,
    nickname: str,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
) -> dict[str, Any]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                config_row = await _upsert_and_get_guild_config(
                    conn,
                    guild_id=guild_id,
                    default_item_name=default_item_name,
                    default_allow_random_rob=default_allow_random_rob,
                    default_allow_random_give=default_allow_random_give,
                )
                player_row = await _upsert_and_get_player(
                    conn,
                    guild_id=guild_id,
                    user_id=user_id,
                    nickname=nickname,
                )
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(
            "讀取 Bread 購買上下文失敗。",
            original_exception=exc,
        ) from exc

    return {
        "config_row": config_row,
        "player_row": player_row,
    }


async def execute_buy_transaction(
    *,
    guild_id: int,
    user_id: int,
    nickname: str,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
    now: datetime,
    delta: int,
    buy_cooldown_until: datetime,
    expected_item_count: int,
    expected_buy_cooldown_until: datetime,
    result_text: str,
    extra_data: dict[str, Any],
) -> dict[str, Any]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                config_row = await _upsert_and_get_guild_config(
                    conn,
                    guild_id=guild_id,
                    default_item_name=default_item_name,
                    default_allow_random_rob=default_allow_random_rob,
                    default_allow_random_give=default_allow_random_give,
                )
                player_row = await _upsert_and_get_player(
                    conn,
                    guild_id=guild_id,
                    user_id=user_id,
                    nickname=nickname,
                )

                updated_item_count = int(player_row["item_count"]) + delta
                updated_row = await conn.fetchrow(
                    """
                    UPDATE bread_players
                    SET
                        item_count = $3,
                        buy_cooldown_until = $4,
                        updated_at = $5
                    WHERE
                        guild_id = $1
                        AND user_id = $2
                        AND item_count = $6
                        AND buy_cooldown_until = $7
                    RETURNING
                        guild_id,
                        user_id,
                        nickname,
                        level,
                        xp,
                        item_count,
                        buy_cooldown_until
                    """,
                    guild_id,
                    user_id,
                    updated_item_count,
                    buy_cooldown_until,
                    now,
                    expected_item_count,
                    expected_buy_cooldown_until,
                )
                if updated_row is None:
                    latest_player_row = await conn.fetchrow(
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
                    if latest_player_row is None:
                        raise DatabaseOperationError("更新 Bread 玩家資料失敗。")

                    return {
                        "config_row": config_row,
                        "player_row": latest_player_row,
                        "updated_row": None,
                        "state_changed": True,
                    }

                await conn.execute(
                    """
                    INSERT INTO bread_action_logs (
                        guild_id,
                        actor_user_id,
                        target_user_id,
                        action_type,
                        delta,
                        result_text,
                        extra_data,
                        created_at
                    )
                    VALUES ($1, $2, NULL, $3, $4, $5, $6::jsonb, $7)
                    """,
                    guild_id,
                    user_id,
                    "buy",
                    delta,
                    result_text,
                    extra_data,
                    now,
                )
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(
            "執行 Bread 購買交易失敗。",
            original_exception=exc,
        ) from exc

    return {
        "config_row": config_row,
        "player_row": player_row,
        "updated_row": updated_row,
        "state_changed": False,
    }


async def _upsert_and_get_guild_config(
    conn: Any,
    *,
    guild_id: int,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
) -> "asyncpg.Record":
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
        raise DatabaseOperationError("找不到 Bread 群設定。")
    return config_row


async def _upsert_and_get_player(
    conn: Any,
    *,
    guild_id: int,
    user_id: int,
    nickname: str,
) -> "asyncpg.Record":
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
    if player_row is None:
        raise DatabaseOperationError("找不到 Bread 玩家資料。")
    return player_row
