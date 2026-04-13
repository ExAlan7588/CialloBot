from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import randint, random

from bread.constants import (
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_ITEM_NAME,
    DEFAULT_MAX_ROB_AMOUNT,
    DEFAULT_MIN_ROB_AMOUNT,
    DEFAULT_ROB_COOLDOWN_SECONDS,
    DEFAULT_ROB_POLICE_EXTRA_COOLDOWN_SECONDS,
)
from bread.repositories.player_action_repository import execute_transfer_action
from bread.repositories.player_context_repository import get_transfer_context
from bread.services.gameplay_utils import (
    EPOCH_UTC,
    build_feature_disabled_error,
    build_player_state,
    ensure_guild_supported,
    get_remaining_cooldown_text,
    resolve_state_change_conflict,
)
from utils.exceptions import BusinessError


@dataclass(frozen=True, slots=True)
class RobResult:
    item_name: str
    actor_delta: int
    target_delta: int
    previous_item_count: int
    current_item_count: int
    target_user_id: int
    target_nickname: str
    event_name: str
    message: str
    cooldown_until: datetime
    was_random_target: bool


async def rob_items(
    *,
    guild_id: int | None,
    actor_user_id: int,
    actor_nickname: str,
    target_user_id: int | None,
) -> RobResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    now = datetime.now(timezone.utc)
    rob_amount = randint(DEFAULT_MIN_ROB_AMOUNT, DEFAULT_MAX_ROB_AMOUNT)

    try:
        context = await get_transfer_context(
            guild_id=resolved_guild_id,
            actor_user_id=actor_user_id,
            actor_nickname=actor_nickname,
            target_user_id=target_user_id,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
            min_target_item_count=rob_amount,
            allow_random=target_user_id is None,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error(exc) from exc

    config_row = context["config_row"]
    actor_row = context["actor_row"]
    target_row = context["target_row"]
    was_random_target = bool(context["was_random_target"])
    item_name = str(config_row["item_name"])
    allow_random_rob = bool(config_row["allow_random_rob"])
    previous_item_count = int(actor_row["item_count"])
    cooldown_until = actor_row["rob_cooldown_until"]

    if isinstance(cooldown_until, datetime) and cooldown_until > now:
        raise BusinessError(
            f"無法搶{item_name}，還有{get_remaining_cooldown_text(cooldown_until, now=now)}",
            author_name="冷卻中",
        )

    if target_user_id is None and not allow_random_rob:
        raise BusinessError("你還沒有指定要搶的玩家。", author_name="缺少對象")
    if target_row is None and target_user_id is not None:
        raise BusinessError(f"該玩家沒有足夠的 {item_name} 可以搶。", author_name="找不到目標")
    if target_row is None:
        raise BusinessError(
            f"這個群目前沒有可搶的玩家，大家的 {item_name} 都太少了。",
            author_name="找不到目標",
        )

    target_id = int(target_row["user_id"])
    target_name = str(target_row["nickname"])
    target_previous_item_count = int(target_row["item_count"])
    if target_previous_item_count < rob_amount:
        raise BusinessError(f"該玩家沒有那麼多 {item_name} 可以搶。", author_name="存貨不足")

    actor_delta = rob_amount
    target_delta = -rob_amount
    cooldown_seconds = DEFAULT_ROB_COOLDOWN_SECONDS
    refresh_eat_cooldown = False
    event_name = "normal_rob"

    roll = random()
    if roll < 0.05:
        special = randint(1, 3)
        if special == 1:
            if previous_item_count > rob_amount:
                actor_delta = -rob_amount
                target_delta = rob_amount
                event_name = "caught_and_fined"
        elif special == 2:
            if target_previous_item_count > rob_amount * 2:
                actor_delta = rob_amount * 2
                target_delta = -(rob_amount * 2)
                event_name = "big_success"
        else:
            actor_delta = 0
            target_delta = 0
            refresh_eat_cooldown = True
            event_name = "refresh_eat"
    elif roll < 0.07:
        actor_delta = 0
        target_delta = 0
        cooldown_seconds = DEFAULT_ROB_COOLDOWN_SECONDS + DEFAULT_ROB_POLICE_EXTRA_COOLDOWN_SECONDS
        event_name = "rob_police"
    elif roll < 0.09:
        loss_amount = min(rob_amount, previous_item_count)
        actor_delta = -loss_amount
        target_delta = loss_amount
        event_name = "counterattack"
    elif roll < 0.1:
        cooldown_seconds = 0
        event_name = "rob_again"

    actor_state = build_player_state(actor_row)
    actor_state["item_count"] = previous_item_count + actor_delta
    actor_state["rob_cooldown_until"] = now + timedelta(seconds=cooldown_seconds)
    if refresh_eat_cooldown:
        actor_state["eat_cooldown_until"] = EPOCH_UTC

    target_state = build_player_state(target_row)
    target_state["item_count"] = target_previous_item_count + target_delta

    message = _build_rob_message(
        item_name=item_name,
        target_nickname=target_name,
        actor_delta=actor_delta,
        current_item_count=actor_state["item_count"],
        was_random_target=was_random_target,
        event_name=event_name,
    )

    try:
        tx_result = await execute_transfer_action(
            guild_id=resolved_guild_id,
            actor_user_id=actor_user_id,
            target_user_id=target_id,
            actor_expected_updated_at=actor_row["updated_at"],
            target_expected_updated_at=target_row["updated_at"],
            actor_new_state=actor_state,
            target_new_state=target_state,
            action_type="rob",
            delta=actor_delta,
            result_text=message,
            extra_data={
                "event_name": event_name,
                "rob_amount": rob_amount,
                "actor_delta": actor_delta,
                "target_delta": target_delta,
                "target_user_id": target_id,
                "target_nickname": target_name,
                "was_random_target": was_random_target,
                "previous_item_count": previous_item_count,
                "current_item_count": actor_state["item_count"],
            },
            now=now,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error(exc) from exc

    if tx_result["state_changed"]:
        resolve_state_change_conflict(
            item_name=item_name,
            action_name="搶",
            latest_row=tx_result["latest_actor_row"],
            cooldown_key="rob_cooldown_until",
            now=now,
        )

    actor_updated_row = tx_result["actor_updated_row"]
    return RobResult(
        item_name=item_name,
        actor_delta=actor_delta,
        target_delta=target_delta,
        previous_item_count=previous_item_count,
        current_item_count=int(actor_updated_row["item_count"]),
        target_user_id=target_id,
        target_nickname=target_name,
        event_name=event_name,
        message=message,
        cooldown_until=actor_updated_row["rob_cooldown_until"],
        was_random_target=was_random_target,
    )


def _build_rob_message(
    *,
    item_name: str,
    target_nickname: str,
    actor_delta: int,
    current_item_count: int,
    was_random_target: bool,
    event_name: str,
) -> str:
    target_prefix = "隨機對象" if was_random_target else "目標"
    if event_name == "caught_and_fined":
        return (
            f"你搶 {item_name} 被抓到了，反而倒賠給 {target_prefix} [{target_nickname}]。\n"
            f"這次你失去 **{abs(actor_delta)}** 個 {item_name}，現在剩 **{current_item_count}** 個。"
        )
    if event_name == "big_success":
        return (
            f"搶劫大成功！你從 {target_prefix} [{target_nickname}] 那裡直接搶到 **{actor_delta}** 個 {item_name}。\n"
            f"現在你共有 **{current_item_count}** 個 {item_name}。"
        )
    if event_name == "refresh_eat":
        return (
            f"這次什麼都沒搶到，但你突然想吃東西了。\n"
            f"吃 {item_name} 的冷卻已刷新，目前仍持有 **{current_item_count}** 個 {item_name}。"
        )
    if event_name == "rob_police":
        return f"你搶 {item_name} 被警察盯上了，這次沒有損益，但下次搶要多等 40 分鐘。"
    if event_name == "counterattack":
        return (
            f"搶奪失敗，{target_prefix} [{target_nickname}] 反擊成功。\n"
            f"這次你反而丟了 **{abs(actor_delta)}** 個 {item_name}，現在剩 **{current_item_count}** 個。"
        )
    if event_name == "rob_again":
        return (
            f"成功從 {target_prefix} [{target_nickname}] 那裡搶到 **{actor_delta}** 個 {item_name}。\n"
            f"你現在共有 **{current_item_count}** 個 {item_name}，而且這次可以立刻再搶一次。"
        )
    return (
        f"成功從 {target_prefix} [{target_nickname}] 那裡搶到 **{actor_delta}** 個 {item_name}。\n"
        f"你現在共有 **{current_item_count}** 個 {item_name}。"
    )
