from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Any

from bread.constants import DEFAULT_ALLOW_RANDOM_GIVE, DEFAULT_ALLOW_RANDOM_ROB, DEFAULT_ITEM_NAME
from bread.repositories.profile_repository import get_or_create_guild_config, get_or_create_player
from bread.repositories.record_repository import count_user_records, fetch_user_records_page
from utils.exceptions import BusinessError


@dataclass(frozen=True, slots=True)
class BreadRecordEntry:
    action_label: str
    delta: int
    event_name: str | None
    preview_text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BreadRecordPage:
    item_name: str
    nickname: str
    page: int
    total_pages: int
    total_entries: int
    entries: list[BreadRecordEntry]


async def get_record_page(
    *,
    guild_id: int | None,
    user_id: int,
    nickname: str,
    page: int,
    page_size: int = 5,
) -> BreadRecordPage:
    if guild_id is None:
        raise BusinessError("Bread 功能目前只能在伺服器內使用。", author_name="無法使用")

    normalized_page = max(page, 1)

    try:
        # 先确保群配置和玩家档案存在，这样空记录页面也能正常展示物品名和昵称。
        config_row = await get_or_create_guild_config(
            guild_id,
            default_item_name=DEFAULT_ITEM_NAME,
            default_allow_random_rob=DEFAULT_ALLOW_RANDOM_ROB,
            default_allow_random_give=DEFAULT_ALLOW_RANDOM_GIVE,
        )
        player_row = await get_or_create_player(
            guild_id,
            user_id,
            nickname=nickname,
        )
        total_entries = await count_user_records(guild_id=guild_id, user_id=user_id)
    except RuntimeError as exc:
        raise BusinessError(
            "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
            author_name="功能未啟用",
        ) from exc

    total_pages = max(ceil(total_entries / page_size), 1)
    current_page = min(normalized_page, total_pages)
    offset = (current_page - 1) * page_size

    try:
        rows = await fetch_user_records_page(
            guild_id=guild_id,
            user_id=user_id,
            limit=page_size,
            offset=offset,
        )
    except RuntimeError as exc:
        raise BusinessError(
            "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
            author_name="功能未啟用",
        ) from exc

    entries = [_build_record_entry(row) for row in rows]
    return BreadRecordPage(
        item_name=str(config_row["item_name"]),
        nickname=str(player_row["nickname"]),
        page=current_page,
        total_pages=total_pages,
        total_entries=total_entries,
        entries=entries,
    )


def _build_record_entry(row: Any) -> BreadRecordEntry:
    extra_data = row["extra_data"]
    event_name: str | None = None
    if isinstance(extra_data, dict):
        raw_event_name = extra_data.get("event_name")
        if isinstance(raw_event_name, str) and raw_event_name:
            event_name = raw_event_name

    return BreadRecordEntry(
        action_label=_map_action_label(str(row["action_type"])),
        delta=int(row["delta"]),
        event_name=event_name,
        preview_text=_build_preview_text(str(row["result_text"])),
        created_at=row["created_at"],
    )


def _map_action_label(action_type: str) -> str:
    mapping = {
        "buy": "購買",
        "eat": "食用",
        "rob": "搶奪",
        "give": "贈送",
        "bet": "賭局",
        "rename": "改名",
    }
    return mapping.get(action_type, action_type)


def _build_preview_text(result_text: str, *, limit: int = 70) -> str:
    # 记录页只保留第一行摘要，避免分页 embed 被长文案撑爆。
    first_line = result_text.strip().splitlines()[0] if result_text.strip() else "沒有結果摘要。"
    compact_text = " ".join(first_line.split())
    if len(compact_text) <= limit:
        return compact_text
    return f"{compact_text[: limit - 1]}…"
