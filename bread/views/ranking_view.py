from __future__ import annotations

import discord
from discord.ext import commands

from bread.services.ranking_service import RankingPage, RankingScope, get_ranking_page
from utils.base_view import BaseView


class BreadRankingView(BaseView):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        author: discord.User | discord.Member,
        scope: RankingScope,
        guild_id: int | None,
        page_size: int = 10,
    ) -> None:
        super().__init__(bot=bot, author=author, timeout=300.0)
        self.scope: RankingScope = scope
        self.guild_id = guild_id
        self.page_size = page_size
        self.current_page = 1
        self.total_pages = 1

    async def build_embed(self) -> discord.Embed:
        ranking_page = await get_ranking_page(
            scope=self.scope,
            guild_id=self.guild_id,
            page=self.current_page,
            page_size=self.page_size,
        )
        self.current_page = ranking_page.page
        self.total_pages = ranking_page.total_pages
        self._refresh_button_states()
        return self._build_embed_from_page(ranking_page)

    def _build_embed_from_page(self, ranking_page: RankingPage) -> discord.Embed:
        scope_name = "群排行榜" if ranking_page.scope == "group" else "全局排行榜"
        if ranking_page.scope == "global":
            title = f"Bread {scope_name}"
            description = "全局榜按同一位玩家跨群匯總。"
        else:
            title = f"{ranking_page.item_name} {scope_name}"
            description = "排序規則：先等級，再物品數量。"

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple(),
        )

        if not ranking_page.entries:
            embed.add_field(
                name="目前沒有資料",
                value="先使用 `/bread profile` 建立玩家資料，再回來看排行榜。",
                inline=False,
            )
        else:
            lines: list[str] = []
            for entry in ranking_page.entries:
                if ranking_page.scope == "global":
                    extra = f" | 跨 {entry.guild_count} 個群" if entry.guild_count else ""
                    lines.append(
                        f"`#{entry.rank:>2}` <@{entry.user_id}> | Lv.{entry.level} | "
                        f"{entry.item_count} 個{extra}"
                    )
                else:
                    lines.append(
                        f"`#{entry.rank:>2}` {entry.nickname} (<@{entry.user_id}>) | "
                        f"Lv.{entry.level} | {entry.item_count} 個"
                    )

            embed.add_field(name="排名", value="\n".join(lines), inline=False)

        embed.set_footer(
            text=(
                f"第 {ranking_page.page}/{ranking_page.total_pages} 頁"
                f" | 共 {ranking_page.total_entries} 筆"
            )
        )
        return embed

    def _refresh_button_states(self) -> None:
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages

    async def on_timeout(self) -> None:
        self.disable_items()
        if self.message is None:
            return

        try:
            await self.message.edit(view=self)
        except discord.NotFound:
            return

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if self.current_page <= 1:
            await interaction.response.defer()
            return

        self.current_page -= 1
        embed = await self.build_embed()
        await self.absolute_edit(interaction, embed=embed, view=self)

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.secondary)
    async def next_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if self.current_page >= self.total_pages:
            await interaction.response.defer()
            return

        self.current_page += 1
        embed = await self.build_embed()
        await self.absolute_edit(interaction, embed=embed, view=self)


async def create_ranking_response(
    *,
    bot: commands.Bot,
    author: discord.User | discord.Member,
    scope: RankingScope,
    guild_id: int | None,
) -> tuple[discord.Embed, BreadRankingView]:
    view = BreadRankingView(
        bot=bot,
        author=author,
        scope=scope,
        guild_id=guild_id,
    )

    try:
        embed = await view.build_embed()
    except Exception:
        view.stop()
        raise

    if not view.total_pages:
        view.total_pages = 1
        view._refresh_button_states()

    return embed, view
