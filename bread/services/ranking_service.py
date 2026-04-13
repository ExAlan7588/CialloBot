from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

from bread.constants import DEFAULT_ITEM_NAME
from bread.repositories.profile_repository import get_or_create_guild_config
from bread.repositories.ranking_repository import (
    count_global_players,
    count_group_players,
    fetch_global_ranking_page,
    fetch_group_ranking_page,
)
from utils.exceptions import BusinessError


RankingScope = Literal["group", "global"]


@dataclass(frozen=True, slots=True)
class RankingEntry:
    rank: int
    user_id: int
    nickname: str
    level: int
    item_count: int
    guild_count: int | None = None


@dataclass(frozen=True, slots=True)
class RankingPage:
    scope: RankingScope
    page: int
    total_pages: int
    total_entries: int
    item_name: str
    entries: list[RankingEntry]


async def get_ranking_page(
    *,
    scope: RankingScope,
    guild_id: int | None,
    page: int,
    page_size: int = 10,
) -> RankingPage:
    if page < 1:
        raise BusinessError("頁碼必須大於 0。", author_name="頁碼錯誤")

    if scope == "group":
        if guild_id is None:
            raise BusinessError(
                "群排行榜只能在伺服器內使用。",
                author_name="無法使用",
            )

        try:
            config_row = await get_or_create_guild_config(
                guild_id,
                default_item_name=DEFAULT_ITEM_NAME,
                default_allow_random_rob=True,
                default_allow_random_give=True,
            )
            total_entries = await count_group_players(guild_id)
            total_pages = max(1, ceil(total_entries / page_size)) if total_entries else 1
            current_page = min(page, total_pages)
            offset = (current_page - 1) * page_size
            rows = await fetch_group_ranking_page(
                guild_id,
                limit=page_size,
                offset=offset,
            )
            item_name = str(config_row["item_name"])
        except RuntimeError as exc:
            raise BusinessError(
                "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
                author_name="功能未啟用",
            ) from exc

        entries = [
            RankingEntry(
                rank=offset + index + 1,
                user_id=int(row["user_id"]),
                nickname=str(row["nickname"]),
                level=int(row["level"]),
                item_count=int(row["item_count"]),
            )
            for index, row in enumerate(rows)
        ]
        return RankingPage(
            scope=scope,
            page=current_page,
            total_pages=total_pages,
            total_entries=total_entries,
            item_name=item_name,
            entries=entries,
        )

    try:
        total_entries = await count_global_players()
        total_pages = max(1, ceil(total_entries / page_size)) if total_entries else 1
        current_page = min(page, total_pages)
        offset = (current_page - 1) * page_size
        rows = await fetch_global_ranking_page(limit=page_size, offset=offset)
    except RuntimeError as exc:
        raise BusinessError(
            "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
            author_name="功能未啟用",
        ) from exc

    entries = [
        RankingEntry(
            rank=offset + index + 1,
            user_id=int(row["user_id"]),
            nickname=str(row["nickname"]),
            level=int(row["level"]),
            item_count=int(row["item_count"]),
            guild_count=int(row["guild_count"]),
        )
        for index, row in enumerate(rows)
    ]
    return RankingPage(
        scope=scope,
        page=current_page,
        total_pages=total_pages,
        total_entries=total_entries,
        item_name=DEFAULT_ITEM_NAME,
        entries=entries,
    )
