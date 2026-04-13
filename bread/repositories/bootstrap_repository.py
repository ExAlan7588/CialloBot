from __future__ import annotations

from typing import Final

from database.postgresql.async_manager import get_pool
from utils.exceptions import DatabaseOperationError

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS bread_guild_configs (
        guild_id BIGINT PRIMARY KEY,
        item_name TEXT NOT NULL,
        allow_random_rob BOOLEAN NOT NULL,
        allow_random_give BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bread_players (
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        nickname TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0,
        item_count INTEGER NOT NULL DEFAULT 0,
        buy_cooldown_until TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ 'epoch',
        eat_cooldown_until TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ 'epoch',
        rob_cooldown_until TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ 'epoch',
        give_cooldown_until TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ 'epoch',
        bet_cooldown_until TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ 'epoch',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bread_action_logs (
        id BIGSERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        actor_user_id BIGINT NOT NULL,
        target_user_id BIGINT NULL,
        action_type TEXT NOT NULL,
        delta INTEGER NOT NULL,
        result_text TEXT NOT NULL,
        extra_data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bread_action_logs_guild_actor_created_at
    ON bread_action_logs (guild_id, actor_user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bread_players_group_rank
    ON bread_players (guild_id, level DESC, item_count DESC, user_id ASC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bread_players_global_rank
    ON bread_players (user_id, level DESC, item_count DESC)
    """,
]

SCHEMA_INIT_ERROR: Final = "初始化 Bread 資料表失敗。"


async def ensure_bread_schema() -> None:
    pool = get_pool()

    try:
        async with pool.acquire() as conn, conn.transaction():
            for statement in _SCHEMA_STATEMENTS:
                await conn.execute(statement)
    except Exception as exc:
        raise DatabaseOperationError(SCHEMA_INIT_ERROR, original_exception=exc) from exc
