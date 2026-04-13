from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from bread.repositories.bootstrap_repository import ensure_bread_schema
from bread.services.bet_service import bet_items
from bread.services.buy_service import buy_items
from bread.services.eat_service import eat_items
from bread.services.give_service import give_items
from bread.services.profile_service import get_profile_data
from bread.services.rob_service import rob_items
from bread.services.settings_service import set_bread_nickname, set_guild_item_name
from bread.constants import GESTURE_PAPER, GESTURE_ROCK, GESTURE_SCISSORS
from bread.views.record_view import create_record_response
from bread.views.ranking_view import create_ranking_response
from utils.exceptions import BusinessError
from utils.response_embeds import SuccessEmbed, WarningEmbed


class BreadCog(commands.Cog):
    bread_group = app_commands.Group(name="bread", description="Bread 商店玩法")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @bread_group.command(name="profile", description="查看 Bread 玩家資料")
    @app_commands.describe(member="要查看的成員，留空則查看自己")
    async def bread_profile(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        target = member or interaction.user
        profile_data = await get_profile_data(
            guild_id=interaction.guild_id,
            user_id=target.id,
            nickname=target.display_name,
        )

        item_name = profile_data["item_name"]
        embed = SuccessEmbed(
            author_name=f"{profile_data['nickname']} 的 {item_name} 檔案",
            description=(
                f"目前擁有 **{profile_data['item_count']}** 個 {item_name}\n"
                f"等級：**Lv.{profile_data['level']}**\n"
                f"經驗：**{profile_data['xp']} / {profile_data['level_target']}**\n"
                f"再吃 **{profile_data['remaining_to_level']}** 個 {item_name} 可以升級"
            ),
        )
        embed.set_footer(text="Bread Phase 2: profile")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bread_group.command(name="buy", description="購買 Bread 物品")
    async def bread_buy(self, interaction: discord.Interaction) -> None:
        result = await buy_items(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            nickname=interaction.user.display_name,
        )

        if result.delta > 0:
            embed = SuccessEmbed(
                author_name=f"{interaction.user.display_name} 的 {result.item_name} 採購結果",
                description=result.message,
            )
        else:
            embed = WarningEmbed(
                author_name=f"{interaction.user.display_name} 的 {result.item_name} 採購結果",
                description=result.message,
            )

        embed.set_footer(
            text=(
                f"事件: {result.event_name}"
                f" | 持有量 {result.previous_item_count} -> {result.current_item_count}"
            )
        )

        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="eat", description="吃掉 Bread 物品")
    async def bread_eat(self, interaction: discord.Interaction) -> None:
        result = await eat_items(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            nickname=interaction.user.display_name,
        )

        embed = SuccessEmbed(
            author_name=f"{interaction.user.display_name} 的 {result.item_name} 食用結果",
            description=result.message,
        )
        embed.set_footer(
            text=(
                f"事件: {result.event_name}"
                f" | 持有量 {result.previous_item_count} -> {result.current_item_count}"
                f" | Lv.{result.previous_level} -> Lv.{result.current_level}"
            )
        )
        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="give", description="贈送 Bread 物品")
    @app_commands.describe(member="要送出的對象，留空則隨機贈送")
    async def bread_give(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if member is not None and member.id == interaction.user.id:
            raise BusinessError("無法送自己哦。", author_name="操作失敗")
        if member is not None and member.bot:
            raise BusinessError("不能贈送給機器人哦。", author_name="操作失敗")

        target_id = member.id if member else None
        result = await give_items(
            guild_id=interaction.guild_id,
            actor_user_id=interaction.user.id,
            actor_nickname=interaction.user.display_name,
            target_user_id=target_id,
        )

        embed = SuccessEmbed(
            author_name=f"{interaction.user.display_name} 的 {result.item_name} 贈送結果",
            description=result.message,
        )
        embed.set_footer(
            text=(
                f"事件: {result.event_name}"
                f" | 自己 {result.previous_item_count} -> {result.current_item_count}"
                f" | 對象: {result.target_nickname}"
            )
        )
        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="rob", description="搶奪 Bread 物品")
    @app_commands.describe(member="要搶奪的對象，留空則隨機搶奪")
    async def bread_rob(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if member is not None and member.id == interaction.user.id:
            raise BusinessError("無法搶自己哦。", author_name="操作失敗")
        if member is not None and member.bot:
            raise BusinessError("不能搶機器人哦。", author_name="操作失敗")

        target_id = member.id if member else None
        result = await rob_items(
            guild_id=interaction.guild_id,
            actor_user_id=interaction.user.id,
            actor_nickname=interaction.user.display_name,
            target_user_id=target_id,
        )

        embed_cls = SuccessEmbed if result.actor_delta > 0 else WarningEmbed
        embed = embed_cls(
            author_name=f"{interaction.user.display_name} 的 {result.item_name} 搶奪結果",
            description=result.message,
        )
        embed.set_footer(
            text=(
                f"事件: {result.event_name}"
                f" | 自己 {result.previous_item_count} -> {result.current_item_count}"
                f" | 對象: {result.target_nickname}"
            )
        )
        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="bet", description="賭 Bread 物品")
    @app_commands.describe(gesture="你要出的手勢")
    @app_commands.choices(
        gesture=[
            app_commands.Choice(name=GESTURE_SCISSORS, value=GESTURE_SCISSORS),
            app_commands.Choice(name=GESTURE_ROCK, value=GESTURE_ROCK),
            app_commands.Choice(name=GESTURE_PAPER, value=GESTURE_PAPER),
        ]
    )
    async def bread_bet(
        self,
        interaction: discord.Interaction,
        gesture: app_commands.Choice[str],
    ) -> None:
        result = await bet_items(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            nickname=interaction.user.display_name,
            gesture=gesture.value,
        )

        embed_cls = SuccessEmbed if result.delta > 0 else WarningEmbed
        embed = embed_cls(
            author_name=f"{interaction.user.display_name} 的 {result.item_name} 賭局結果",
            description=result.message,
        )
        embed.set_footer(
            text=(
                f"事件: {result.event_name}"
                f" | 持有量 {result.previous_item_count} -> {result.current_item_count}"
                f" | 出拳 {result.player_gesture}/{result.system_gesture}"
            )
        )
        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="nickname", description="設定 Bread 暱稱")
    @app_commands.describe(name="新的 Bread 暱稱")
    async def bread_nickname(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        result = await set_bread_nickname(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            display_name=interaction.user.display_name,
            new_nickname=name,
        )
        embed = SuccessEmbed(
            author_name="Bread 暱稱已更新",
            description=f"已將暱稱從 **{result.old_nickname}** 改成 **{result.new_nickname}**。",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bread_group.command(name="itemname", description="設定本群 Bread 物品名稱")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(name="新的群自訂物品名")
    async def bread_item_name(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        result = await set_guild_item_name(
            guild_id=interaction.guild_id,
            item_name=name,
        )
        embed = SuccessEmbed(
            author_name="Bread 群物品已更新",
            description=(
                f"本群物品名稱已從 **{result.old_item_name}** 改成 **{result.new_item_name}**。\n"
                f"之後 `/bread buy`、`/bread eat` 等指令都會使用新名稱。"
            ),
        )
        await interaction.response.send_message(embed=embed)

    @bread_group.command(name="rank", description="查看 Bread 排行榜")
    @app_commands.describe(scope="要查看群排行榜還是全局排行榜")
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="群排行榜", value="group"),
            app_commands.Choice(name="全局排行榜", value="global"),
        ]
    )
    async def bread_rank(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] | None = None,
    ) -> None:
        selected_scope = scope.value if scope else "group"
        embed, view = await create_ranking_response(
            bot=self.bot,
            author=interaction.user,
            scope=selected_scope,  # type: ignore[arg-type]
            guild_id=interaction.guild_id,
        )

        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @bread_group.command(name="record", description="查看 Bread 行為紀錄")
    @app_commands.describe(member="要查看的成員，留空則查看自己")
    async def bread_record(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        target = member or interaction.user
        embed, view = await create_record_response(
            bot=self.bot,
            author=interaction.user,
            target=target,
            guild_id=interaction.guild_id,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    try:
        await ensure_bread_schema()
    except RuntimeError:
        logger.warning("BreadCog 載入時未偵測到 PostgreSQL，先跳過 schema bootstrap")

    await bot.add_cog(BreadCog(bot))
    logger.info("BreadCog loaded.")
