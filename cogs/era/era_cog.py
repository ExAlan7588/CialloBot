"""Era TW Discord Cog

主要的 Discord Cog，提供 /era 系列 Slash Commands。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from .managers.game_manager import GameManager
from .managers.character_manager import CharacterManager
from .managers.command_manager import CommandManager
from .ui.views import MainMenuView, CharacterSelectView
from .ui.embeds import EraEmbeds

if TYPE_CHECKING:
    from bot import OsuBot


class EraCog(commands.Cog, name="Era"):
    """eraTW Discord 遊戲 Cog

    提供 eraTW 遊戲的 Discord 介面。
    """

    def __init__(self, bot: "OsuBot"):
        """初始化 Era Cog

        Args:
            bot: Discord Bot 實例
        """
        self.bot = bot

        # 遊戲管理器
        self.game_manager = GameManager()
        self.character_manager: CharacterManager | None = None
        self.command_manager: CommandManager | None = None

        # 是否已初始化
        self._initialized = False

    async def cog_load(self) -> None:
        """Cog 載入時執行"""
        logger.info("正在載入 Era Cog...")

        # 嘗試找到 eraTW 資料路徑
        possible_paths = [
            Path("eraTW"),
            Path("./eraTW"),
            Path(__file__).parent.parent.parent.parent / "eraTW",
        ]

        era_path = None
        for path in possible_paths:
            if path.exists():
                era_path = path
                break

        # 初始化遊戲管理器
        success = await self.game_manager.initialize(era_path)
        if success:
            self.character_manager = CharacterManager(self.game_manager)
            self.command_manager = CommandManager(self.game_manager, self.character_manager)
            self._initialized = True
            logger.info("Era Cog 初始化完成")
        else:
            logger.warning("Era Cog 初始化失敗，使用有限功能模式")

    async def cog_unload(self) -> None:
        """Cog 卸載時執行"""
        logger.info("Era Cog 已卸載")

    # === Slash Commands ===

    era_group = app_commands.Group(name="era", description="eraTW 幻想鄉生活模擬遊戲")

    @era_group.command(name="start", description="開始新遊戲")
    async def era_start(self, interaction: discord.Interaction):
        """開始新遊戲"""
        if not self._initialized:
            await interaction.response.send_message(
                embed=EraEmbeds.error("遊戲系統未初始化，請稍後再試"), ephemeral=True
            )
            return

        discord_id = interaction.user.id
        discord_name = interaction.user.display_name

        # 檢查是否已有存檔
        if self.game_manager.has_save(discord_id):
            await interaction.response.send_message(
                embed=EraEmbeds.info(
                    "已有存檔",
                    "你已經有遊戲存檔了。\n使用 `/era continue` 繼續遊戲，或 `/era reset` 重新開始。",
                ),
                ephemeral=True,
            )
            return

        # 創建新遊戲
        save = self.game_manager.create_new_game(discord_id, discord_name)

        # 顯示歡迎訊息
        embed = EraEmbeds.new_game_welcome()
        view = MainMenuView(
            discord_id, self.game_manager, self.character_manager, self.command_manager
        )

        await interaction.response.send_message(embed=embed, view=view)

    @era_group.command(name="continue", description="繼續遊戲")
    async def era_continue(self, interaction: discord.Interaction):
        """繼續遊戲"""
        if not self._initialized:
            await interaction.response.send_message(
                embed=EraEmbeds.error("遊戲系統未初始化，請稍後再試"), ephemeral=True
            )
            return

        discord_id = interaction.user.id

        # 檢查是否有存檔
        if not self.game_manager.has_save(discord_id):
            await interaction.response.send_message(
                embed=EraEmbeds.info(
                    "沒有存檔", "你還沒有遊戲存檔。\n使用 `/era start` 開始新遊戲。"
                ),
                ephemeral=True,
            )
            return

        # 顯示主選單
        save = self.game_manager.get_player_save(discord_id)
        embed = EraEmbeds.main_menu(save)
        view = MainMenuView(
            discord_id, self.game_manager, self.character_manager, self.command_manager
        )

        await interaction.response.send_message(embed=embed, view=view)

    @era_group.command(name="status", description="查看遊戲狀態")
    async def era_status(self, interaction: discord.Interaction):
        """查看遊戲狀態"""
        if not self._initialized:
            await interaction.response.send_message(
                embed=EraEmbeds.error("遊戲系統未初始化"), ephemeral=True
            )
            return

        discord_id = interaction.user.id
        save = self.game_manager.get_player_save(discord_id)

        if not save:
            await interaction.response.send_message(
                embed=EraEmbeds.error("找不到存檔，請先使用 `/era start` 開始遊戲"), ephemeral=True
            )
            return

        embed = EraEmbeds.main_menu(save)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @era_group.command(name="characters", description="查看角色列表")
    async def era_characters(self, interaction: discord.Interaction):
        """查看角色列表"""
        if not self._initialized:
            await interaction.response.send_message(
                embed=EraEmbeds.error("遊戲系統未初始化"), ephemeral=True
            )
            return

        discord_id = interaction.user.id

        if not self.game_manager.has_save(discord_id):
            await interaction.response.send_message(
                embed=EraEmbeds.error("找不到存檔，請先使用 `/era start` 開始遊戲"), ephemeral=True
            )
            return

        characters = self.character_manager.get_characters_by_affection(discord_id)
        embed = EraEmbeds.character_list(characters)

        view = CharacterSelectView(
            discord_id, self.game_manager, self.character_manager, self.command_manager, characters
        )

        await interaction.response.send_message(embed=embed, view=view)

    @era_group.command(name="reset", description="重置遊戲（刪除存檔）")
    async def era_reset(self, interaction: discord.Interaction):
        """重置遊戲"""
        discord_id = interaction.user.id

        if not self.game_manager.has_save(discord_id):
            await interaction.response.send_message(
                embed=EraEmbeds.error("你沒有存檔可以重置"), ephemeral=True
            )
            return

        # 確認重置
        confirm_embed = discord.Embed(
            title="⚠️ 確認重置",
            description="確定要刪除你的遊戲存檔嗎？\n此操作無法撤銷！",
            color=0xFF4444,
        )

        class ConfirmView(discord.ui.View):
            def __init__(self, game_manager: GameManager):
                super().__init__(timeout=30)
                self.game_manager = game_manager
                self.confirmed = False

            @discord.ui.button(label="確認刪除", style=discord.ButtonStyle.danger)
            async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                self.game_manager.delete_save(inter.user.id)
                await inter.response.edit_message(
                    embed=EraEmbeds.info(
                        "重置完成", "你的存檔已被刪除。使用 `/era start` 開始新遊戲。"
                    ),
                    view=None,
                )
                self.confirmed = True
                self.stop()

            @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter: discord.Interaction, btn: discord.ui.Button):
                await inter.response.edit_message(
                    embed=EraEmbeds.info("已取消", "你的存檔保持不變。"), view=None
                )
                self.stop()

        view = ConfirmView(self.game_manager)
        await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)

    @era_group.command(name="help", description="查看遊戲說明")
    async def era_help(self, interaction: discord.Interaction):
        """查看遊戲說明"""
        embed = discord.Embed(
            title="📖 eraTW 遊戲說明",
            description="歡迎來到幻想鄉！這是一款文字冒險遊戲。",
            color=0xFF6B9D,
        )

        embed.add_field(
            name="🎮 基本操作",
            value=(
                "`/era start` - 開始新遊戲\n"
                "`/era continue` - 繼續遊戲\n"
                "`/era status` - 查看狀態\n"
                "`/era characters` - 角色列表\n"
                "`/era reset` - 重置遊戲"
            ),
            inline=False,
        )

        embed.add_field(
            name="💕 好感度系統",
            value=(
                "與角色互動可以增加好感度：\n"
                "• 0-99: 陌生人\n"
                "• 100-299: 認識\n"
                "• 300-499: 朋友\n"
                "• 500-699: 好友\n"
                "• 700-899: 親密\n"
                "• 900+: 戀人 ❤️"
            ),
            inline=False,
        )

        embed.add_field(
            name="⏰ 時間系統",
            value="遊戲中的時間會隨著你的行動流逝。不同時段可以遇到不同的角色。",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "OsuBot"):
    """設置 Era Cog（供 discord.py 自動載入）"""
    await bot.add_cog(EraCog(bot))
