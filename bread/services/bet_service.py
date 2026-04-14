from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import choice, randint, random

from bread.constants import (
    ALL_GESTURES,
    DEFAULT_ALLOW_RANDOM_GIVE,
    DEFAULT_ALLOW_RANDOM_ROB,
    DEFAULT_BET_COOLDOWN_SECONDS,
    DEFAULT_BET_POLICE_EXTRA_COOLDOWN_SECONDS,
    DEFAULT_ITEM_NAME,
    DEFAULT_MAX_BET_AMOUNT,
    DEFAULT_MIN_BET_AMOUNT,
    GESTURE_PAPER,
    GESTURE_ROCK,
    GESTURE_SCISSORS,
)
from bread.repositories.player_action_repository import execute_single_player_action
from bread.repositories.player_context_repository import get_or_create_player_context
from bread.services.gameplay_utils import (
    build_feature_disabled_error,
    build_player_state,
    ensure_guild_supported,
    raise_cooldown_error,
    resolve_state_change_conflict,
)
from utils.exceptions import BusinessError


@dataclass(frozen=True, slots=True)
class BetResult:
    actor_nickname: str
    item_name: str
    delta: int
    previous_item_count: int
    current_item_count: int
    player_gesture: str
    system_gesture: str
    event_name: str
    message: str
    cooldown_until: datetime


WINNING_GESTURES = {
    GESTURE_SCISSORS: GESTURE_PAPER,
    GESTURE_ROCK: GESTURE_SCISSORS,
    GESTURE_PAPER: GESTURE_ROCK,
}


async def bet_items(
    *, guild_id: int | None, user_id: int, fallback_nickname: str, gesture: str
) -> BetResult:
    resolved_guild_id = ensure_guild_supported(guild_id)
    if gesture not in ALL_GESTURES:
        error_message = "手勢必須是剪刀、石頭或布。"
        raise BusinessError(error_message, author_name="手勢無效")

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
    cooldown_until = player_row["bet_cooldown_until"]

    if isinstance(cooldown_until, datetime) and cooldown_until > now:
        raise_cooldown_error(
            action_name="賭",
            item_name=item_name,
            cooldown_until=cooldown_until,
            now=now,
        )

    bet_amount = randint(DEFAULT_MIN_BET_AMOUNT, DEFAULT_MAX_BET_AMOUNT)
    if previous_item_count < bet_amount:
        error_message = f"你的 {item_name} 不夠賭，先去買一些吧。"
        raise BusinessError(error_message, author_name="存貨不足")

    system_gesture = choice(list(ALL_GESTURES))
    delta, base_event_name = _resolve_base_bet_outcome(
        gesture=gesture, system_gesture=system_gesture, bet_amount=bet_amount
    )
    cooldown_seconds = DEFAULT_BET_COOLDOWN_SECONDS if delta != 0 else 0
    event_name = base_event_name

    roll = random()
    if roll < 0.04:
        if base_event_name == "win" and previous_item_count > bet_amount * 2:
            delta *= 2
            event_name = "double_win"
        else:
            delta = -bet_amount
            cooldown_seconds = DEFAULT_BET_COOLDOWN_SECONDS
            event_name = "triple_hands_loss"
    elif roll < 0.07:
        delta = 0
        cooldown_seconds = (
            DEFAULT_BET_COOLDOWN_SECONDS + DEFAULT_BET_POLICE_EXTRA_COOLDOWN_SECONDS
        )
        event_name = "bet_police"
    elif roll < 0.1:
        cooldown_seconds = 0
        event_name = "bet_again"

    player_state = build_player_state(player_row)
    player_state["item_count"] = previous_item_count + delta
    player_state["bet_cooldown_until"] = now + timedelta(seconds=cooldown_seconds)

    message = _build_bet_message(
        item_name=item_name,
        previous_item_count=previous_item_count,
        current_item_count=player_state["item_count"],
        player_gesture=gesture,
        system_gesture=system_gesture,
        delta=delta,
        bet_amount=bet_amount,
        event_name=event_name,
    )

    try:
        tx_result = await execute_single_player_action(
            guild_id=resolved_guild_id,
            user_id=user_id,
            expected_updated_at=player_row["updated_at"],
            new_state=player_state,
            action_type="bet",
            delta=delta,
            result_text=message,
            extra_data={
                "event_name": event_name,
                "player_gesture": gesture,
                "system_gesture": system_gesture,
                "bet_amount": bet_amount,
                "previous_item_count": previous_item_count,
                "current_item_count": player_state["item_count"],
            },
            now=now,
        )
    except RuntimeError as exc:
        raise build_feature_disabled_error() from exc

    if tx_result["state_changed"]:
        resolve_state_change_conflict(
            item_name=item_name,
            action_name="賭",
            latest_row=tx_result["latest_row"],
            cooldown_key="bet_cooldown_until",
            now=now,
        )

    updated_row = tx_result["updated_row"]
    return BetResult(
        actor_nickname=str(updated_row["nickname"]),
        item_name=item_name,
        delta=delta,
        previous_item_count=previous_item_count,
        current_item_count=int(updated_row["item_count"]),
        player_gesture=gesture,
        system_gesture=system_gesture,
        event_name=event_name,
        message=message,
        cooldown_until=updated_row["bet_cooldown_until"],
    )


def _resolve_base_bet_outcome(
    *, gesture: str, system_gesture: str, bet_amount: int
) -> tuple[int, str]:
    if WINNING_GESTURES[gesture] == system_gesture:
        return bet_amount, "win"
    if WINNING_GESTURES[system_gesture] == gesture:
        return -bet_amount, "lose"
    return 0, "draw"


def _build_bet_message(
    *,
    item_name: str,
    previous_item_count: int,
    current_item_count: int,
    player_gesture: str,
    system_gesture: str,
    delta: int,
    bet_amount: int,
    event_name: str,
) -> str:
    if event_name == "double_win":
        return (
            f"你出 {player_gesture}，我出 {system_gesture}。\n"
            f"你贏了，還觸發加碼！直接拿到 **{delta}** 個 {item_name}。\n"
            f"持有量：**{previous_item_count} -> {current_item_count}**"
        )
    if event_name == "triple_hands_loss":
        return (
            f"你出 {player_gesture}，我出了三隻手，這把算你輸。\n"
            f"你失去 **{bet_amount}** 個 {item_name}，現在剩 **{current_item_count}** 個。"
        )
    if event_name == "bet_police":
        return (
            f"你出 {player_gesture}，我出 {system_gesture}。\n"
            f"被警察盯上了，這把不算輸贏，但下次賭要多等 40 分鐘。"
        )
    if event_name == "bet_again":
        suffix = (
            "平局，這次可以立刻再來一把。"
            if delta == 0
            else "你有點上癮，這次可以立刻再來一把。"
        )
        return (
            f"你出 {player_gesture}，我出 {system_gesture}。\n"
            f"{_build_base_bet_outcome_text(item_name=item_name, delta=delta, current_item_count=current_item_count)}\n"
            f"{suffix}"
        )
    return (
        f"你出 {player_gesture}，我出 {system_gesture}。\n"
        f"{_build_base_bet_outcome_text(item_name=item_name, delta=delta, current_item_count=current_item_count)}"
    )


def _build_base_bet_outcome_text(
    *, item_name: str, delta: int, current_item_count: int
) -> str:
    if delta > 0:
        return f"你贏了，拿到 **{delta}** 個 {item_name}，現在共有 **{current_item_count}** 個。"
    if delta < 0:
        return f"你輸了，失去 **{abs(delta)}** 個 {item_name}，現在剩 **{current_item_count}** 個。"
    return f"平局，{item_name} 全數退回，你現在仍有 **{current_item_count}** 個。"
    return f"平手，{item_name} 原數退回，你手上還是 **{current_item_count}** 個。"
