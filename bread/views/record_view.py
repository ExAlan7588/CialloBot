from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bread.services.record_service import BreadRecordPage, get_record_page
from utils.base_view import BaseView

if TYPE_CHECKING:
    from discord.ext import commands


class BreadRecordView(BaseView):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        author: discord.User | discord.Member,
        target: discord.User | discord.Member,
        guild_id: int | None,
        page_size: int = 5,
    ) -> None:
        super().__init__(bot=bot, author=author, timeout=300.0)
        self.target = target
        self.guild_id = guild_id
        self.page_size = page_size
        self.current_page = 1
        self.total_pages = 1

    async def build_embed(self) -> discord.Embed:
        record_page = await get_record_page(
            guild_id=self.guild_id,
            user_id=self.target.id,
            nickname=self.target.display_name,
            page=self.current_page,
            page_size=self.page_size,
        )
        self.current_page = record_page.page
        self.total_pages = record_page.total_pages
        self._refresh_button_states()
        return self._build_embed_from_page(record_page)

    def _build_embed_from_page(self, record_page: BreadRecordPage) -> discord.Embed:
        embed = discord.Embed(
            title=f"{record_page.nickname} 的 {record_page.item_name} 行為紀錄",
            description="只顯示目前已接進 Bread 資料表的行為。",
            color=discord.Color.gold(),
        )

        if not record_page.entries:
            embed.add_field(
                name="目前沒有紀錄",
                value="先使用 `/bread buy`，之後再補其他 Bread 指令後，這裡會持續累積。",
                inline=False,
            )
        else:
            lines: list[str] = []
            for entry in record_page.entries:
                created_at_text = discord.utils.format_dt(entry.created_at, style="f")
                delta_text = f"{entry.delta:+d}"
                event_text = f" | `{entry.event_name}`" if entry.event_name else ""
                lines.append(
                    f"{created_at_text} | {entry.action_label} | `{delta_text}`{event_text}\n"
                    f"{entry.preview_text}"
                )

            embed.add_field(name="最近紀錄", value="\n\n".join(lines), inline=False)

        embed.set_footer(
            text=(
                f"第 {record_page.page}/{record_page.total_pages} 頁"
                f" | 共 {record_page.total_entries} 筆"
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


async def create_record_response(
    *,
    bot: commands.Bot,
    author: discord.User | discord.Member,
    target: discord.User | discord.Member,
    guild_id: int | None,
) -> tuple[discord.Embed, BreadRecordView]:
    view = BreadRecordView(
        bot=bot,
        author=author,
        target=target,
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
