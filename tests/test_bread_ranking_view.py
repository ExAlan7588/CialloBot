from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast

import discord
from discord.ext import commands

from bread.services.ranking_service import RankingEntry, RankingPage
from bread.views.ranking_view import BreadRankingView


class BreadRankingViewTitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_ranking_title_uses_guild_item_name(self) -> None:
        view = BreadRankingView(
            bot=cast(commands.Bot, SimpleNamespace()),
            author=cast(discord.User, SimpleNamespace()),
            scope="group",
            guild_id=123,
        )
        embed = view._build_embed_from_page(
            RankingPage(
                scope="group",
                page=1,
                total_pages=1,
                total_entries=1,
                item_name="可頌",
                entries=[
                    RankingEntry(
                        rank=1,
                        user_id=1,
                        nickname="BreadPlayer",
                        level=2,
                        item_count=5,
                    )
                ],
            )
        )

        self.assertEqual(embed.title, "可頌 群排行榜")

    async def test_global_ranking_title_does_not_fall_back_to_default_item_name(self) -> None:
        view = BreadRankingView(
            bot=cast(commands.Bot, SimpleNamespace()),
            author=cast(discord.User, SimpleNamespace()),
            scope="global",
            guild_id=123,
        )
        embed = view._build_embed_from_page(
            RankingPage(
                scope="global",
                page=1,
                total_pages=1,
                total_entries=1,
                item_name="面包",
                entries=[
                    RankingEntry(
                        rank=1,
                        user_id=1,
                        nickname="BreadPlayer",
                        level=2,
                        item_count=5,
                        guild_count=3,
                    )
                ],
            )
        )

        self.assertEqual(embed.title, "Bread 全局排行榜")


if __name__ == "__main__":
    unittest.main()
