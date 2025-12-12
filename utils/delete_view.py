"""通用刪除訊息視圖

此模組提供一個可重用的刪除按鈕視圖，用於各種指令觸發的訊息。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from discord import Interaction


class DeleteMessageView(discord.ui.View):
    """刪除訊息視圖 - 用於指令觸發的訊息

    此視圖提供一個「刪除」按鈕，允許觸發指令的用戶或管理員刪除機器人的回覆訊息。

    特點：
    - 權限控制：只有觸發者或管理員可以刪除
    - 自動超時：5 分鐘後按鈕失效
    - 完整的錯誤處理
    - 日誌記錄
    """

    def __init__(
        self, trigger_user_id: int, guild: discord.Guild | None, timeout: float = 300.0
    ) -> None:
        """初始化刪除視圖

        Args:
            trigger_user_id: 觸發指令的用戶 ID
            guild: 伺服器對象（用於檢查管理員權限）
            timeout: 按鈕超時時間（秒），默認 300 秒（5 分鐘）
        """
        super().__init__(timeout=timeout)
        self.trigger_user_id = trigger_user_id
        self.guild = guild

    def is_admin(self, member: discord.Member) -> bool:
        """檢查用戶是否為管理員

        管理員定義：
        1. 伺服器擁有者
        2. 擁有「管理員」權限的成員

        Args:
            member: Discord 成員對象

        Returns:
            是否為管理員
        """
        if not self.guild:
            return False

        # 檢查是否為伺服器擁有者
        if self.guild.owner_id == member.id:
            return True

        # 檢查是否有管理員權限
        return bool(member.guild_permissions.administrator)

    @discord.ui.button(label="刪除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(
        self, interaction: Interaction, button: discord.ui.Button
    ) -> None:
        """刪除按鈕回調

        Args:
            interaction: Discord 互動對象
            button: 按鈕對象
        """
        # 檢查權限：觸發者或管理員
        is_trigger_user = interaction.user.id == self.trigger_user_id
        is_admin = False

        if isinstance(interaction.user, discord.Member):
            is_admin = self.is_admin(interaction.user)

        if not is_trigger_user and not is_admin:
            await interaction.response.send_message(
                "❌ 只有觸發此指令的用戶或管理員才能刪除此訊息！", ephemeral=True
            )
            logger.debug(
                f"🚫 用戶 {interaction.user} 嘗試刪除訊息但無權限 "
                f"(觸發者: {self.trigger_user_id})"
            )
            return

        # 刪除訊息
        try:
            message_id = interaction.message.id
            await interaction.message.delete()

            logger.info(
                f"🗑️ 用戶 {interaction.user} ({interaction.user.id}) "
                f"刪除了指令觸發的訊息 (ID: {message_id})"
            )

            # 發送確認訊息（因為原訊息已刪除，所以用 ephemeral）
            await interaction.response.send_message(
                "✅ 已成功刪除訊息！", ephemeral=True
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ 訊息已被刪除或不存在。", ephemeral=True
            )
            logger.warning(f"⚠️ 用戶 {interaction.user} 嘗試刪除訊息但訊息不存在")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 機器人沒有權限刪除此訊息。", ephemeral=True
            )
            logger.error(f"❌ 機器人沒有權限刪除訊息 (ID: {interaction.message.id})")
        except Exception as e:
            logger.error(f"❌ 刪除訊息時發生錯誤: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ 刪除訊息時發生錯誤，請稍後再試。", ephemeral=True
            )

    async def on_timeout(self) -> None:
        """超時處理 - 禁用所有按鈕"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        logger.debug(
            f"⏱️ DeleteMessageView 超時，按鈕已禁用 (觸發者: {self.trigger_user_id})"
        )
