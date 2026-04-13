from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands

from bread.services.record_service import BreadRecordEntry, BreadRecordPage
from bread.views.record_view import BreadRecordView


class BreadRecordViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_embed_uses_fallback_nickname_for_bootstrap(self) -> None:
        target = cast(discord.User, SimpleNamespace(id=456, display_name="DiscordActor"))
        view = BreadRecordView(
            bot=cast(commands.Bot, SimpleNamespace()),
            author=cast(discord.User, SimpleNamespace()),
            target=target,
            guild_id=123,
        )
        record_page = BreadRecordPage(
            item_name="可頌",
            nickname="BreadActor",
            page=1,
            total_pages=1,
            total_entries=1,
            entries=[
                BreadRecordEntry(
                    action_label="購買",
                    delta=3,
                    event_name="normal_buy",
                    preview_text="成功購買 3 個可頌。",
                    created_at=datetime(2026, 4, 13, 9, 0, tzinfo=UTC),
                )
            ],
        )

        with patch(
            "bread.views.record_view.get_record_page",
            AsyncMock(return_value=record_page),
        ) as mocked_get_record_page:
            embed = await view.build_embed()

        mocked_get_record_page.assert_awaited_once_with(
            guild_id=123,
            user_id=456,
            fallback_nickname="DiscordActor",
            page=1,
            page_size=5,
        )
        self.assertEqual(embed.title, "BreadActor 的 可頌 行為紀錄")


if __name__ == "__main__":
    unittest.main()
