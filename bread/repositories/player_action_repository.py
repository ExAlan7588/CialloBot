from __future__ import annotations

from datetime import datetime
from typing import Any

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

from bread.repositories.shared_state_repository import fetch_player


class _StateChangedError(Exception):
    pass


PLAYER_STATE_COLUMNS = (
    "nickname",
    "level",
    "xp",
    "item_count",
    "buy_cooldown_until",
    "eat_cooldown_until",
    "rob_cooldown_until",
    "give_cooldown_until",
    "bet_cooldown_until",
)


async def execute_single_player_action(
    *,
    guild_id: int,
    user_id: int,
    expected_updated_at: datetime,
    new_state: dict[str, Any],
    action_type: str,
    delta: int,
    result_text: str,
    extra_data: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            try:
                async with conn.transaction():
                    updated_row = await _update_player_state(
                        conn,
                        guild_id=guild_id,
                        user_id=user_id,
                        expected_updated_at=expected_updated_at,
                        new_state=new_state,
                        now=now,
                    )
                    if updated_row is None:
                        raise _StateChangedError

                    await _insert_action_log(
                        conn,
                        guild_id=guild_id,
                        actor_user_id=user_id,
                        target_user_id=None,
                        action_type=action_type,
                        delta=delta,
                        result_text=result_text,
                        extra_data=extra_data,
                        now=now,
                    )
            except _StateChangedError:
                latest_row = await fetch_player(
                    conn,
                    guild_id=guild_id,
                    user_id=user_id,
                )
                return {
                    "updated_row": None,
                    "latest_row": latest_row,
                    "state_changed": True,
                }
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(
            f"執行 Bread {action_type} 操作失敗。",
            original_exception=exc,
        ) from exc

    return {
        "updated_row": updated_row,
        "latest_row": updated_row,
        "state_changed": False,
    }


async def execute_transfer_action(
    *,
    guild_id: int,
    actor_user_id: int,
    target_user_id: int,
    actor_expected_updated_at: datetime,
    target_expected_updated_at: datetime,
    actor_new_state: dict[str, Any],
    target_new_state: dict[str, Any],
    action_type: str,
    delta: int,
    result_text: str,
    extra_data: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            try:
                async with conn.transaction():
                    actor_updated_row = await _update_player_state(
                        conn,
                        guild_id=guild_id,
                        user_id=actor_user_id,
                        expected_updated_at=actor_expected_updated_at,
                        new_state=actor_new_state,
                        now=now,
                    )
                    if actor_updated_row is None:
                        raise _StateChangedError

                    target_updated_row = await _update_player_state(
                        conn,
                        guild_id=guild_id,
                        user_id=target_user_id,
                        expected_updated_at=target_expected_updated_at,
                        new_state=target_new_state,
                        now=now,
                    )
                    if target_updated_row is None:
                        raise _StateChangedError

                    await _insert_action_log(
                        conn,
                        guild_id=guild_id,
                        actor_user_id=actor_user_id,
                        target_user_id=target_user_id,
                        action_type=action_type,
                        delta=delta,
                        result_text=result_text,
                        extra_data=extra_data,
                        now=now,
                    )
            except _StateChangedError:
                latest_actor_row = await fetch_player(
                    conn,
                    guild_id=guild_id,
                    user_id=actor_user_id,
                )
                latest_target_row = await fetch_player(
                    conn,
                    guild_id=guild_id,
                    user_id=target_user_id,
                )
                return {
                    "actor_updated_row": None,
                    "target_updated_row": None,
                    "latest_actor_row": latest_actor_row,
                    "latest_target_row": latest_target_row,
                    "state_changed": True,
                }
    except DatabaseOperationError:
        raise
    except Exception as exc:
        raise DatabaseOperationError(
            f"執行 Bread {action_type} 操作失敗。",
            original_exception=exc,
        ) from exc

    return {
        "actor_updated_row": actor_updated_row,
        "target_updated_row": target_updated_row,
        "latest_actor_row": actor_updated_row,
        "latest_target_row": target_updated_row,
        "state_changed": False,
    }


async def _update_player_state(
    conn,
    *,
    guild_id: int,
    user_id: int,
    expected_updated_at: datetime,
    new_state: dict[str, Any],
    now: datetime,
):
    _validate_state(new_state)

    return await conn.fetchrow(
        """
        UPDATE bread_players
        SET
            nickname = $3,
            level = $4,
            xp = $5,
            item_count = $6,
            buy_cooldown_until = $7,
            eat_cooldown_until = $8,
            rob_cooldown_until = $9,
            give_cooldown_until = $10,
            bet_cooldown_until = $11,
            updated_at = $12
        WHERE guild_id = $1 AND user_id = $2 AND updated_at = $13
        RETURNING
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
        """,
        guild_id,
        user_id,
        new_state["nickname"],
        new_state["level"],
        new_state["xp"],
        new_state["item_count"],
        new_state["buy_cooldown_until"],
        new_state["eat_cooldown_until"],
        new_state["rob_cooldown_until"],
        new_state["give_cooldown_until"],
        new_state["bet_cooldown_until"],
        now,
        expected_updated_at,
    )


async def _insert_action_log(
    conn,
    *,
    guild_id: int,
    actor_user_id: int,
    target_user_id: int | None,
    action_type: str,
    delta: int,
    result_text: str,
    extra_data: dict[str, Any],
    now: datetime,
) -> None:
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
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        """,
        guild_id,
        actor_user_id,
        target_user_id,
        action_type,
        delta,
        result_text,
        extra_data,
        now,
    )


def _validate_state(new_state: dict[str, Any]) -> None:
    missing_columns = [column for column in PLAYER_STATE_COLUMNS if column not in new_state]
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise DatabaseOperationError(f"Bread 玩家狀態欄位缺失: {missing_text}")
