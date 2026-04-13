from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from bread.constants import DEFAULT_ALLOW_RANDOM_GIVE, DEFAULT_ALLOW_RANDOM_ROB, DEFAULT_ITEM_NAME
from bread.repositories.player_action_repository import execute_single_player_action
from bread.repositories.player_context_repository import get_or_create_player_context
from bread.repositories.profile_repository import get_or_create_guild_config
from bread.services.gameplay_utils import (
    build_feature_disabled_error,
    build_player_state,
    ensure_guild_supported,
    raise_state_changed_error,
)
from database.postgresql.async_manager import get_pool
from utils.exceptions import BusinessError, DatabaseOperationError


@dataclass(frozen=True, slots=True)
class NicknameUpdateResult:
    old_nickname: str
    new_nickname: str


@dataclass(frozen=True, slots=True)
class ItemNameUpdateResult:
    old_item_name: str
    new_item_name: str


EMPTY_NICKNAME_ERROR: Final = "暱稱不能是空的。"
LONG_NICKNAME_ERROR: Final = "Bread 暱稱不可大於 7 個字。"
ITEM_NAME_LENGTH_ERROR: Final = "自訂物品名稱長度必須介於 2 到 5 個字。"
ITEM_NAME_UPDATE_ERROR: Final = "更新 Bread 群物品名稱失敗。"


async def set_bread_nickname(
    *, guild_id: int | None, user_id: int, fallback_nickname: str, new_nickname: str
) -> NicknameUpdateResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    normalized_nickname = new_nickname.strip()
    if not normalized_nickname:
        raise BusinessError(EMPTY_NICKNAME_ERROR, author_name="暱稱無效")
    if len(normalized_nickname) > 7:
        raise BusinessError(LONG_NICKNAME_ERROR, author_name="暱稱無效")

    now = datetime.now(UTC)
    try:
        context = await get_or_create_player_context(
            guild_id=resolved_guild_id,
            user_id=user_id,
            fallback_nickname=fallback_nickname,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    player_row = context["player_row"]
    old_nickname = str(player_row["nickname"])
    player_state = build_player_state(player_row)
    player_state["nickname"] = normalized_nickname
    result_text = f"將 Bread 暱稱從 {old_nickname} 改成 {normalized_nickname}"

    try:
        tx_result = await execute_single_player_action(
            guild_id=resolved_guild_id,
            user_id=user_id,
            expected_updated_at=player_row["updated_at"],
            new_state=player_state,
            action_type="rename",
            delta=0,
            result_text=result_text,
            extra_data={
                "event_name": "rename_nickname",
                "old_nickname": old_nickname,
                "new_nickname": normalized_nickname,
            },
            now=now,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    if tx_result["state_changed"]:
        raise_state_changed_error()

    return NicknameUpdateResult(old_nickname=old_nickname, new_nickname=normalized_nickname)


async def set_guild_item_name(*, guild_id: int | None, item_name: str) -> ItemNameUpdateResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    normalized_item_name = item_name.strip()
    if len(normalized_item_name) < 2 or len(normalized_item_name) > 5:
        raise BusinessError(ITEM_NAME_LENGTH_ERROR, author_name="名稱無效")

    try:
        config_row = await get_or_create_guild_config(
            resolved_guild_id,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    old_item_name = str(config_row["item_name"])
    now = datetime.now(UTC)

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE bread_guild_configs
                SET item_name = $2, updated_at = $3
                WHERE guild_id = $1
                """,
                resolved_guild_id,
                normalized_item_name,
                now,
            )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc
    except Exception as exc:
        raise DatabaseOperationError(ITEM_NAME_UPDATE_ERROR, original_exception=exc) from exc

    return ItemNameUpdateResult(old_item_name=old_item_name, new_item_name=normalized_item_name)
