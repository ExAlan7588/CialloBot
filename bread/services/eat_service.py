from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import randint, random

from bread.constants import (
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_EAT_COOLDOWN_SECONDS,
    DEFAULT_EAT_EXTRA_COOLDOWN_SECONDS,
    DEFAULT_EAT_HUNGRY_THRESHOLD,
    DEFAULT_ITEM_NAME,
    DEFAULT_LEVEL_BREAD_NUM,
    DEFAULT_MAX_EAT_AMOUNT,
    DEFAULT_MIN_EAT_AMOUNT,
)
from bread.repositories.player_action_repository import execute_single_player_action
from bread.repositories.player_context_repository import get_or_create_player_context
from bread.services.gameplay_utils import (
    EPOCH_UTC,
    build_feature_disabled_error,
    build_player_state,
    ensure_guild_supported,
    raise_cooldown_error,
    resolve_state_change_conflict,
)
from utils.exceptions import BusinessError


@dataclass(frozen=True, slots=True)
class EatResult:
    actor_nickname: str
    item_name: str
    consumed_amount: int
    previous_item_count: int
    current_item_count: int
    previous_level: int
    current_level: int
    previous_xp: int
    current_xp: int
    event_name: str
    message: str
    cooldown_until: datetime


async def eat_items(*, guild_id: int | None, user_id: int, fallback_nickname: str) -> EatResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
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

    config_row = context["config_row"]
    player_row = context["player_row"]
    item_name = str(config_row["item_name"])
    previous_item_count = int(player_row["item_count"])
    previous_level = int(player_row["level"])
    previous_xp = int(player_row["xp"])
    cooldown_until = player_row["eat_cooldown_until"]

    if isinstance(cooldown_until, datetime) and cooldown_until > now:
        raise_cooldown_error(
            action_name="吃", item_name=item_name, cooldown_until=cooldown_until, now=now
        )

    eat_amount = randint(DEFAULT_MIN_EAT_AMOUNT, DEFAULT_MAX_EAT_AMOUNT)
    if previous_item_count < eat_amount:
        error_message = f"你的{item_name}還不夠吃，先去買一些吧。"
        raise BusinessError(error_message, author_name="存貨不足")

    player_state = build_player_state(player_row)
    event = _resolve_eat_event(previous_item_count=previous_item_count, eat_amount=eat_amount)

    consumed_amount = int(event["consumed_amount"])
    player_state["item_count"] = previous_item_count - consumed_amount

    actual_level_delta = int(event["level_delta"])
    if actual_level_delta < 0:
        actual_level_delta = max(-previous_level, actual_level_delta)
    player_state["level"] = previous_level + actual_level_delta
    player_state["xp"] = previous_xp + consumed_amount

    extra_level_ups = 0
    while player_state["xp"] >= DEFAULT_LEVEL_BREAD_NUM:
        player_state["xp"] -= DEFAULT_LEVEL_BREAD_NUM
        player_state["level"] += 1
        extra_level_ups += 1

    if bool(event["reset_all_cooldowns"]):
        player_state["buy_cooldown_until"] = EPOCH_UTC
        player_state["rob_cooldown_until"] = EPOCH_UTC
        player_state["give_cooldown_until"] = EPOCH_UTC
        player_state["bet_cooldown_until"] = EPOCH_UTC
    if bool(event["refresh_rob_cooldown"]):
        player_state["rob_cooldown_until"] = EPOCH_UTC

    cooldown_seconds = int(event["cooldown_seconds"])
    player_state["eat_cooldown_until"] = now + timedelta(seconds=cooldown_seconds)
    message = _build_eat_message(
        item_name=item_name,
        previous_item_count=previous_item_count,
        current_item_count=player_state["item_count"],
        previous_level=previous_level,
        current_level=player_state["level"],
        consumed_amount=consumed_amount,
        event_name=str(event["event_name"]),
        extra_level_ups=extra_level_ups,
    )

    try:
        tx_result = await execute_single_player_action(
            guild_id=resolved_guild_id,
            user_id=user_id,
            expected_updated_at=player_row["updated_at"],
            new_state=player_state,
            action_type="eat",
            delta=-consumed_amount,
            result_text=message,
            extra_data={
                "event_name": event["event_name"],
                "consumed_amount": consumed_amount,
                "previous_item_count": previous_item_count,
                "current_item_count": player_state["item_count"],
                "previous_level": previous_level,
                "current_level": player_state["level"],
                "previous_xp": previous_xp,
                "current_xp": player_state["xp"],
            },
            now=now,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    if tx_result["state_changed"]:
        resolve_state_change_conflict(
            item_name=item_name,
            action_name="吃",
            latest_row=tx_result["latest_row"],
            cooldown_key="eat_cooldown_until",
            now=now,
        )

    updated_row = tx_result["updated_row"]
    return EatResult(
        actor_nickname=str(updated_row["nickname"]),
        item_name=item_name,
        consumed_amount=consumed_amount,
        previous_item_count=previous_item_count,
        current_item_count=int(updated_row["item_count"]),
        previous_level=previous_level,
        current_level=int(updated_row["level"]),
        previous_xp=previous_xp,
        current_xp=int(updated_row["xp"]),
        event_name=str(event["event_name"]),
        message=message,
        cooldown_until=updated_row["eat_cooldown_until"],
    )


def _resolve_eat_event(*, previous_item_count: int, eat_amount: int) -> dict[str, int | bool | str]:
    roll = random()

    if roll < 0.01:
        return {
            "event_name": "super_bread",
            "consumed_amount": eat_amount,
            "level_delta": 1,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.015:
        return {
            "event_name": "bad_bread",
            "consumed_amount": eat_amount,
            "level_delta": -1,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.02:
        return {
            "event_name": "refresh_all",
            "consumed_amount": eat_amount,
            "level_delta": 0,
            "cooldown_seconds": 0,
            "reset_all_cooldowns": True,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.025 and previous_item_count > DEFAULT_MAX_EAT_AMOUNT:
        return {
            "event_name": "spoiled_food",
            "consumed_amount": 0,
            "level_delta": 0,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.03:
        return {
            "event_name": "refresh_rob",
            "consumed_amount": eat_amount,
            "level_delta": 0,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": True,
        }
    if roll < 0.07:
        return {
            "event_name": "eaten_by_shopkeeper",
            "consumed_amount": 0,
            "level_delta": 0,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.1 and previous_item_count >= DEFAULT_MAX_EAT_AMOUNT * 2:
        return {
            "event_name": "too_full",
            "consumed_amount": eat_amount,
            "level_delta": 0,
            "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS + DEFAULT_EAT_EXTRA_COOLDOWN_SECONDS,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }
    if roll < 0.2:
        return {
            "event_name": "eat_again",
            "consumed_amount": eat_amount,
            "level_delta": 0,
            "cooldown_seconds": 0,
            "reset_all_cooldowns": False,
            "refresh_rob_cooldown": False,
        }

    return {
        "event_name": "normal_eat",
        "consumed_amount": eat_amount,
        "level_delta": 0,
        "cooldown_seconds": DEFAULT_EAT_COOLDOWN_SECONDS,
        "reset_all_cooldowns": False,
        "refresh_rob_cooldown": False,
    }


def _build_eat_message(
    *,
    item_name: str,
    previous_item_count: int,
    current_item_count: int,
    previous_level: int,
    current_level: int,
    consumed_amount: int,
    event_name: str,
    extra_level_ups: int,
) -> str:
    if event_name == "super_bread":
        message = (
            f"成功吃掉 **{consumed_amount}** 個 {item_name}，還吃到超級 {item_name}，額外升了 1 級！\n"
            f"現在還剩 **{current_item_count}** 個 {item_name}，等級是 **Lv.{current_level}**。"
        )
    elif event_name == "bad_bread":
        actual_loss = previous_level - current_level
        if actual_loss > 0:
            message = (
                f"{item_name} 壞掉了！你難受得掉了 **{actual_loss}** 級。\n"
                f"現在還剩 **{current_item_count}** 個 {item_name}，等級是 **Lv.{current_level}**。"
            )
        else:
            message = (
                f"{item_name} 壞掉了，但你的等級已經是最低，沒有再往下掉。\n"
                f"現在還剩 **{current_item_count}** 個 {item_name}。"
            )
    elif event_name == "refresh_all":
        message = (
            f"成功吃掉 **{consumed_amount}** 個 {item_name}！這次特別好吃，所有操作冷卻都刷新了。\n"
            f"現在還剩 **{current_item_count}** 個 {item_name}。"
        )
    elif event_name == "spoiled_food":
        message = (
            f"你剛想吃 {item_name}，結果發現這批壞掉了，這次一口都沒吃成。\n"
            f"目前仍然持有 **{previous_item_count}** 個 {item_name}。"
        )
    elif event_name == "refresh_rob":
        message = (
            f"成功吃掉 **{consumed_amount}** 個 {item_name}！你精神大振，搶奪冷卻也一起刷新了。\n"
            f"現在還剩 **{current_item_count}** 個 {item_name}。"
        )
    elif event_name == "eaten_by_shopkeeper":
        message = (
            f"你正準備吃 {item_name}，結果店長先幫你吃掉了，這次沒有算進你的進度。\n"
            f"目前仍然持有 **{current_item_count}** 個 {item_name}。"
        )
    elif event_name == "too_full":
        message = (
            f"成功吃掉 **{consumed_amount}** 個 {item_name}，但你真的吃太撐了。\n"
            f"現在還剩 **{current_item_count}** 個 {item_name}，下次吃要多等 30 分鐘。"
        )
    elif event_name == "eat_again":
        if previous_item_count > DEFAULT_EAT_HUNGRY_THRESHOLD:
            message = (
                f"成功吃掉 **{consumed_amount}** 個 {item_name}！你存貨太多了，這次允許你立刻再吃一次。\n"
                f"現在還剩 **{current_item_count}** 個 {item_name}。"
            )
        else:
            message = (
                f"成功吃掉 **{consumed_amount}** 個 {item_name}！你還是很餓，這次可以立刻再吃一次。\n"
                f"現在還剩 **{current_item_count}** 個 {item_name}。"
            )
    else:
        message = (
            f"成功吃掉 **{consumed_amount}** 個 {item_name}。\n"
            f"現在還剩 **{current_item_count}** 個 {item_name}，等級是 **Lv.{current_level}**。"
        )

    if extra_level_ups > 0:
        message += f"\n累積進度達標，額外升了 **{extra_level_ups}** 級。"
    return message
