from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Never

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

GUILD_ONLY_ERROR: Final = "Bread 功能目前只能在伺服器內使用。"
FEATURE_DISABLED_ERROR: Final = "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。"
STATE_CHANGED_ERROR: Final = "Bread 狀態剛剛被更新，請再試一次。"

EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)


def ensure_guild_supported(guild_id: int | None) -> int:
    if guild_id is None:
        raise BusinessError(GUILD_ONLY_ERROR, author_name="無法使用")
    return guild_id


def build_feature_disabled_error() -> BusinessError:
    return BusinessError(FEATURE_DISABLED_ERROR, author_name="功能未啟用")


def build_player_state(row: Any) -> dict[str, Any]:
    # 统一复制 Bread 玩家可写状态，避免 service 直接改到 asyncpg.Record 引用。
    return {key: deepcopy(row[key]) for key in PLAYER_STATE_KEYS}


def get_remaining_cooldown_text(cooldown_until: datetime, *, now: datetime) -> str:
    return format_remaining_time(cooldown_until - now)


def format_remaining_time(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def raise_cooldown_error(
    *, action_name: str, item_name: str, cooldown_until: datetime, now: datetime
) -> Never:
    error_message = (
        f"無法{action_name}{item_name}，還有{get_remaining_cooldown_text(cooldown_until, now=now)}"
    )
    raise BusinessError(error_message, author_name="冷卻中")


def raise_state_changed_error() -> Never:
    raise BusinessError(STATE_CHANGED_ERROR, author_name="請重試")


def resolve_state_change_conflict(
    *, item_name: str, action_name: str, latest_row: Any, cooldown_key: str, now: datetime
) -> None:
    if latest_row is None:
        raise_state_changed_error()

    latest_cooldown_until = latest_row[cooldown_key]
    # 如果最新状态已经进入冷却，优先回报真实冷却原因；否则才给通用重试提示。
    if isinstance(latest_cooldown_until, datetime) and latest_cooldown_until > now:
        raise_cooldown_error(
            action_name=action_name,
            item_name=item_name,
            cooldown_until=latest_cooldown_until,
            now=now,
        )

    raise_state_changed_error()
