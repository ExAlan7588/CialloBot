from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.exceptions import BusinessError


PLAYER_STATE_KEYS = (
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

EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


def ensure_guild_supported(guild_id: int | None) -> int:
    if guild_id is None:
        raise BusinessError("Bread 功能目前只能在伺服器內使用。", author_name="無法使用")
    return guild_id


def build_feature_disabled_error(exc: RuntimeError) -> BusinessError:
    return BusinessError(
        "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
        author_name="功能未啟用",
    )


def build_player_state(row: Any) -> dict[str, Any]:
    return {key: deepcopy(row[key]) for key in PLAYER_STATE_KEYS}


def get_remaining_cooldown_text(cooldown_until: datetime, *, now: datetime) -> str:
    return format_remaining_time(cooldown_until - now)


def format_remaining_time(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def resolve_state_change_conflict(
    *,
    item_name: str,
    action_name: str,
    latest_row: Any,
    cooldown_key: str,
    now: datetime,
) -> None:
    if latest_row is None:
        raise BusinessError("Bread 狀態剛剛被更新，請再試一次。", author_name="請重試")

    latest_cooldown_until = latest_row[cooldown_key]
    if isinstance(latest_cooldown_until, datetime) and latest_cooldown_until > now:
        raise BusinessError(
            f"無法{action_name}{item_name}，還有{get_remaining_cooldown_text(latest_cooldown_until, now=now)}",
            author_name="冷卻中",
        )

    raise BusinessError("Bread 狀態剛剛被更新，請再試一次。", author_name="請重試")
