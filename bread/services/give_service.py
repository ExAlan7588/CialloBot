from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import randint, random

from bread.constants import (
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_GIVE_COOLDOWN_SECONDS,
    DEFAULT_ITEM_NAME,
    DEFAULT_MAX_GIVE_AMOUNT,
    DEFAULT_MIN_GIVE_AMOUNT,
)
from bread.repositories.player_action_repository import execute_transfer_action
from bread.repositories.player_context_repository import get_transfer_context
from bread.services.gameplay_utils import (
    build_feature_disabled_error,
    build_player_state,
    ensure_guild_supported,
    raise_cooldown_error,
    resolve_state_change_conflict,
)
from utils.exceptions import BusinessError


@dataclass(frozen=True, slots=True)
class GiveResult:
    actor_nickname: str
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


async def give_items(
    *,
    guild_id: int | None,
    actor_user_id: int,
    actor_fallback_nickname: str,
    target_user_id: int | None,
) -> GiveResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    now = datetime.now(UTC)

    try:
        context = await get_transfer_context(
            guild_id=resolved_guild_id,
            actor_user_id=actor_user_id,
            actor_fallback_nickname=actor_fallback_nickname,
            target_user_id=target_user_id,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
            min_target_item_count=0,
            allow_random=target_user_id is None,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    config_row = context["config_row"]
    actor_row = context["actor_row"]
    target_row = context["target_row"]
    was_random_target = bool(context["was_random_target"])
    item_name = str(config_row["item_name"])
    allow_random_give = bool(config_row["allow_random_give"])
    previous_item_count = int(actor_row["item_count"])
    cooldown_until = actor_row["give_cooldown_until"]

    if isinstance(cooldown_until, datetime) and cooldown_until > now:
        raise_cooldown_error(
            action_name="送",
            item_name=item_name,
            cooldown_until=cooldown_until,
            now=now,
        )

    if target_user_id is None and not allow_random_give:
        error_message = "你還沒有指定要送的玩家。"
        raise BusinessError(error_message, author_name="缺少對象")
    if target_row is None and target_user_id is not None:
        error_message = f"該玩家還沒有 {item_name} 資料呢。"
        raise BusinessError(error_message, author_name="找不到目標")
    if target_row is None:
        error_message = f"這個群目前沒有其他可送的玩家，先叫大家來玩 {item_name} 吧。"
        raise BusinessError(error_message, author_name="找不到目標")

    give_amount = randint(DEFAULT_MIN_GIVE_AMOUNT, DEFAULT_MAX_GIVE_AMOUNT)
    if previous_item_count < give_amount:
        error_message = f"你的 {item_name} 還不夠送，先去買一些吧。"
        raise BusinessError(error_message, author_name="存貨不足")

    target_id = int(target_row["user_id"])
    target_name = str(target_row["nickname"])
    target_previous_item_count = int(target_row["item_count"])

    actor_cost = give_amount
    target_gain = give_amount
    event_name = "normal_give"
    roll = random()
    if roll < 0.06:
        bonus_amount = randint(
            DEFAULT_MIN_GIVE_AMOUNT, min(DEFAULT_MAX_GIVE_AMOUNT, previous_item_count)
        )
        actor_cost = -bonus_amount
        event_name = "shopkeeper_bonus"
    elif roll < 0.1:
        special = randint(1, 2)
        if special == 1:
            if previous_item_count > DEFAULT_MAX_GIVE_AMOUNT * 2:
                actor_cost = give_amount * 2
                event_name = "double_cost"
        else:
            actor_cost = 0
            event_name = "no_loss"

    actor_state = build_player_state(actor_row)
    actor_state["item_count"] = previous_item_count - actor_cost
    actor_state["give_cooldown_until"] = now + timedelta(
        seconds=DEFAULT_GIVE_COOLDOWN_SECONDS
    )

    target_state = build_player_state(target_row)
    target_state["item_count"] = target_previous_item_count + target_gain

    message = _build_give_message(
        item_name=item_name,
        target_nickname=target_name,
        give_amount=give_amount,
        actor_cost=actor_cost,
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
            action_type="give",
            delta=-actor_cost,
            result_text=message,
            extra_data={
                "event_name": event_name,
                "give_amount": give_amount,
                "actor_cost": actor_cost,
                "target_gain": target_gain,
                "target_user_id": target_id,
                "target_nickname": target_name,
                "was_random_target": was_random_target,
                "previous_item_count": previous_item_count,
                "current_item_count": actor_state["item_count"],
            },
            now=now,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    if tx_result["state_changed"]:
        resolve_state_change_conflict(
            item_name=item_name,
            action_name="送",
            latest_row=tx_result["latest_actor_row"],
            cooldown_key="give_cooldown_until",
            now=now,
        )

    actor_updated_row = tx_result["actor_updated_row"]
    return GiveResult(
        actor_nickname=str(actor_updated_row["nickname"]),
        item_name=item_name,
        actor_delta=-actor_cost,
        target_delta=target_gain,
        previous_item_count=previous_item_count,
        current_item_count=int(actor_updated_row["item_count"]),
        target_user_id=target_id,
        target_nickname=target_name,
        event_name=event_name,
        message=message,
        cooldown_until=actor_updated_row["give_cooldown_until"],
        was_random_target=was_random_target,
    )


def _build_give_message(
    *,
    item_name: str,
    target_nickname: str,
    give_amount: int,
    actor_cost: int,
    current_item_count: int,
    was_random_target: bool,
    event_name: str,
) -> str:
    target_prefix = "隨機對象" if was_random_target else "目標"
    if event_name == "shopkeeper_bonus":
        return (
            f"你送了 **{give_amount}** 個 {item_name} 給 {target_prefix} [{target_nickname}]。\n"
            f"店長看你人太好，反手又塞了你一些，現在你共有 **{current_item_count}** 個 {item_name}。"
        )
    if event_name == "double_cost":
        return (
            f"你送了 **{give_amount}** 個 {item_name} 給 {target_prefix} [{target_nickname}]。\n"
            f"系統順手又從你這裡拿走同樣一份，這次總共花了 **{actor_cost}** 個 {item_name}。\n"
            f"現在你剩 **{current_item_count}** 個 {item_name}。"
        )
    if event_name == "no_loss":
        return (
            f"你送了 **{give_amount}** 個 {item_name} 給 {target_prefix} [{target_nickname}]。\n"
            f"這次算你善行一件，你自己沒有損失任何 {item_name}。"
        )
    return (
        f"成功贈送 **{give_amount}** 個 {item_name} 給 {target_prefix} [{target_nickname}]。\n"
        f"現在你還有 **{current_item_count}** 個 {item_name}。"
    )
