from __future__ import annotations

from random import randint
from typing import Any, Final

from bread.repositories.shared_state_repository import (
    count_candidate_players,
    fetch_candidate_player_by_offset,
    fetch_player,
    upsert_and_get_guild_config,
    upsert_and_get_player,
)
from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

PLAYER_CONTEXT_ERROR: Final = "讀取 Bread 玩家上下文失敗。"
TRANSFER_CONTEXT_ERROR: Final = "讀取 Bread 互動上下文失敗。"


async def get_or_create_player_context(
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
        async with pool.acquire() as conn, conn.transaction():
            config_row = await upsert_and_get_guild_config(
                conn,
                guild_id=guild_id,
                default_item_name=default_item_name,
                default_allow_random_rob=default_allow_random_rob,
                default_allow_random_give=default_allow_random_give,
            )
            player_row = await upsert_and_get_player(
                conn, guild_id=guild_id, user_id=user_id, nickname=nickname
            )
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(PLAYER_CONTEXT_ERROR, original_exception=exc) from exc

    return {"config_row": config_row, "player_row": player_row}


async def get_transfer_context(
    *,
    guild_id: int,
    actor_user_id: int,
    actor_nickname: str,
    target_user_id: int | None,
    default_item_name: str,
    default_allow_random_rob: bool,
    default_allow_random_give: bool,
    min_target_item_count: int,
    allow_random: bool,
) -> dict[str, Any]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn, conn.transaction():
            config_row = await upsert_and_get_guild_config(
                conn,
                guild_id=guild_id,
                default_item_name=default_item_name,
                default_allow_random_rob=default_allow_random_rob,
                default_allow_random_give=default_allow_random_give,
            )
            actor_row = await upsert_and_get_player(
                conn, guild_id=guild_id, user_id=actor_user_id, nickname=actor_nickname
            )

            target_row = None
            was_random_target = False
            if target_user_id is not None:
                target_row = await fetch_player(conn, guild_id=guild_id, user_id=target_user_id)
            elif allow_random:
                candidate_count = await count_candidate_players(
                    conn,
                    guild_id=guild_id,
                    exclude_user_id=actor_user_id,
                    min_item_count=min_target_item_count,
                )
                if candidate_count > 0:
                    offset = randint(0, candidate_count - 1)
                    target_row = await fetch_candidate_player_by_offset(
                        conn,
                        guild_id=guild_id,
                        exclude_user_id=actor_user_id,
                        min_item_count=min_target_item_count,
                        offset=offset,
                    )
                    was_random_target = target_row is not None
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(TRANSFER_CONTEXT_ERROR, original_exception=exc) from exc

    return {
        "config_row": config_row,
        "actor_row": actor_row,
        "target_row": target_row,
        "was_random_target": was_random_target,
    }
