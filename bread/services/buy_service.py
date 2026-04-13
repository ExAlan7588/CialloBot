from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import randint, random

from bread.constants import (
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_BUY_COOLDOWN_SECONDS,
    DEFAULT_BUY_GOLDEN_BONUS,
    DEFAULT_BUY_LOW_STOCK_BONUS,
    DEFAULT_BUY_LOW_STOCK_THRESHOLD,
    DEFAULT_BUY_TOO_MANY_THRESHOLD,
    DEFAULT_ITEM_NAME,
    DEFAULT_MAX_BUY_AMOUNT,
    DEFAULT_MIN_BUY_AMOUNT,
)
from bread.repositories.buy_repository import execute_buy_transaction, get_or_create_buy_context
from bread.services.gameplay_utils import (
    build_feature_disabled_error,
    ensure_guild_supported,
    raise_cooldown_error,
    resolve_state_change_conflict,
)


@dataclass(frozen=True, slots=True)
class BuyResult:
    actor_nickname: str
    item_name: str
    delta: int
    previous_item_count: int
    current_item_count: int
    event_name: str
    message: str
    cooldown_until: datetime


async def buy_items(*, guild_id: int | None, user_id: int, fallback_nickname: str) -> BuyResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    now = datetime.now(UTC)
    base_amount = randint(DEFAULT_MIN_BUY_AMOUNT, DEFAULT_MAX_BUY_AMOUNT)

    try:
        # 先读取并补齐玩家/群配置，但这里不写入购买结果，也不记录日志。
        context = await get_or_create_buy_context(
            guild_id=resolved_guild_id,
            user_id=user_id,
            fallback_nickname=fallback_nickname,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    config_row = context["config_row"]
    player_row = context["player_row"]
    item_name = str(config_row["item_name"])
    previous_item_count = int(player_row["item_count"])
    cooldown_until = player_row["buy_cooldown_until"]

    if isinstance(cooldown_until, datetime) and cooldown_until > now:
        raise_cooldown_error(
            action_name="買", item_name=item_name, cooldown_until=cooldown_until, now=now
        )

    delta, event_name, message = _resolve_buy_outcome(
        item_name=item_name, previous_item_count=previous_item_count, base_amount=base_amount
    )
    updated_cooldown_until = now + timedelta(seconds=DEFAULT_BUY_COOLDOWN_SECONDS)
    current_item_count = previous_item_count + delta

    try:
        # 真正的库存变化和日志写入只发生在这一段。
        tx_result = await execute_buy_transaction(
            guild_id=resolved_guild_id,
            user_id=user_id,
            fallback_nickname=fallback_nickname,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
            now=now,
            delta=delta,
            buy_cooldown_until=updated_cooldown_until,
            expected_item_count=previous_item_count,
            expected_buy_cooldown_until=cooldown_until,
            result_text=message,
            extra_data={
                "event_name": event_name,
                "base_amount": base_amount,
                "previous_item_count": previous_item_count,
                "current_item_count": current_item_count,
                "item_name": item_name,
            },
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    if tx_result["state_changed"]:
        resolve_state_change_conflict(
            item_name=item_name,
            action_name="買",
            latest_row=tx_result["player_row"],
            cooldown_key="buy_cooldown_until",
            now=now,
        )

    updated_row = tx_result["updated_row"]
    if updated_row is not None:
        current_item_count = int(updated_row["item_count"])

    return BuyResult(
        actor_nickname=str(updated_row["nickname"]),
        item_name=item_name,
        delta=delta,
        previous_item_count=previous_item_count,
        current_item_count=current_item_count,
        event_name=event_name,
        message=message,
        cooldown_until=updated_cooldown_until,
    )


def _resolve_buy_outcome(
    *, item_name: str, previous_item_count: int, base_amount: int
) -> tuple[int, str, str]:
    roll = random()

    if roll < 0.01:
        delta = base_amount + DEFAULT_BUY_GOLDEN_BONUS
        return (
            delta,
            "golden_buy",
            (
                f"出現了黃金{item_name}。本次直接算 **{delta}** 個，"
                f"現在一共擁有 **{previous_item_count + delta}** 個 {item_name}。"
            ),
        )

    if roll < 0.025 and previous_item_count > DEFAULT_MAX_BUY_AMOUNT:
        delta = -base_amount
        return (
            delta,
            "spoiled_stock",
            (
                f"你正想去買{item_name}，結果發現有 **{base_amount}** 個 {item_name} 壞掉了。\n"
                f"現在剩下 **{previous_item_count + delta}** 個 {item_name}。"
            ),
        )

    if roll < 0.2 and previous_item_count < DEFAULT_BUY_LOW_STOCK_THRESHOLD:
        delta = base_amount + DEFAULT_BUY_LOW_STOCK_BONUS
        return (
            delta,
            "low_stock_bonus",
            (
                f"{item_name} 店看你存貨太少，額外送了你一些。\n"
                f"本次共拿到 **{delta}** 個，現在一共擁有 **{previous_item_count + delta}** 個 {item_name}。"
            ),
        )

    if roll < 0.8 and previous_item_count > DEFAULT_BUY_TOO_MANY_THRESHOLD:
        return (
            0,
            "refused_too_many",
            (
                f"你現在的 {item_name} 已經太多了，店家決定先不賣給你。\n"
                f"目前仍然持有 **{previous_item_count}** 個 {item_name}。"
            ),
        )

    return (
        base_amount,
        "normal_buy",
        (
            f"成功購買 **{base_amount}** 個 {item_name}。\n"
            f"現在一共擁有 **{previous_item_count + base_amount}** 個 {item_name}。"
        ),
    )
