"""關鍵詞觸發系統

此 Cog 提供：
1. 伺服器管理員可以添加/刪除/列出關鍵詞
2. 當用戶發送匹配的關鍵詞時，機器人自動回覆
3. 每個伺服器的關鍵詞獨立管理
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
from loguru import logger

if TYPE_CHECKING:
    from discord import Interaction


class DeleteConfirmView(discord.ui.View):
    """刪除確認視圖"""

    def __init__(
        self, message_to_delete: discord.Message, requester: discord.User | discord.Member
    ) -> None:
        """初始化確認視圖

        Args:
            message_to_delete: 要刪除的訊息
            requester: 請求刪除的用戶
        """
        super().__init__(timeout=30.0)
        self.message_to_delete = message_to_delete
        self.requester = requester
        self.value: bool | None = None

    @discord.ui.button(label="確認刪除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """確認刪除按鈕

        Args:
            interaction: Discord 互動對象
            button: 按鈕對象
        """
        from utils.message_tracker import get_message_tracker

        # 驗證是否為請求者
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message(
                "❌ 只有發起刪除請求的用戶才能確認！", ephemeral=True
            )
            return

        try:
            message_id = self.message_to_delete.id
            await self.message_to_delete.delete()

            # 從追蹤器中移除記錄
            tracker = get_message_tracker()
            tracker.remove_message(message_id)

            await interaction.response.send_message("✅ 已成功刪除訊息！", ephemeral=True)
            logger.info(f"🗑️ 用戶 {self.requester} 刪除了機器人訊息 (ID: {message_id})")
        except discord.NotFound:
            await interaction.response.send_message("❌ 訊息已被刪除或不存在。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 機器人沒有權限刪除此訊息。", ephemeral=True)
        except Exception as e:
            logger.error(f"❌ 刪除訊息時發生錯誤: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ 刪除訊息時發生錯誤，請稍後再試。", ephemeral=True
            )
        finally:
            self.value = True
            self.stop()

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """取消按鈕

        Args:
            interaction: Discord 互動對象
            button: 按鈕對象
        """
        # 驗證是否為請求者
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message(
                "❌ 只有發起刪除請求的用戶才能取消！", ephemeral=True
            )
            return

        await interaction.response.send_message("✅ 已取消刪除操作。", ephemeral=True)
        self.value = False
        self.stop()

    async def on_timeout(self) -> None:
        """超時處理"""
        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class KeywordAddModal(Modal, title="新增關鍵詞"):
    """關鍵詞新增 Modal"""

    keyword_input = TextInput(
        label="關鍵詞",
        placeholder="輸入要觸發的關鍵詞...",
        required=True,
        max_length=100,
        style=discord.TextStyle.short,
    )

    response_input = TextInput(
        label="回覆內容",
        placeholder="輸入機器人的回覆內容...",
        required=True,
        max_length=2000,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, cog: KeywordCog) -> None:
        """初始化 Modal

        Args:
            cog: KeywordCog 實例，用於訪問關鍵詞數據
        """
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: Interaction) -> None:
        """處理 Modal 提交

        Args:
            interaction: Discord 互動對象
        """
        keyword = self.keyword_input.value.strip()
        response = self.response_input.value.strip()

        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令只能在伺服器中使用！", ephemeral=True)
            return

        # 獲取伺服器關鍵詞
        guild_keywords = self.cog.get_guild_keywords(interaction.guild.id)

        # 檢查關鍵詞是否已存在
        if keyword in guild_keywords:
            await interaction.response.send_message(
                f"⚠️ 關鍵詞 `{keyword}` 已存在！\n"
                f"當前回覆：{guild_keywords[keyword]}\n\n"
                f"如需修改，請先使用 `/keyword remove` 刪除後再添加。",
                ephemeral=True,
            )
            return

        # 添加關鍵詞
        guild_keywords[keyword] = response
        self.cog.save_keywords()

        await interaction.response.send_message(
            f"✅ 成功添加關鍵詞！\n**關鍵詞：** `{keyword}`\n**回覆：** {response}", ephemeral=True
        )

        logger.info(
            f"➕ 管理員 {interaction.user} 在伺服器 {interaction.guild.name} "
            f"添加關鍵詞: '{keyword}' -> '{response}'"
        )

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        """處理 Modal 錯誤

        Args:
            interaction: Discord 互動對象
            error: 發生的錯誤
        """
        logger.error(f"❌ Modal 提交時發生錯誤: {error}", exc_info=True)

        try:
            await interaction.response.send_message(
                "❌ 處理請求時發生錯誤，請稍後再試。", ephemeral=True
            )
        except discord.InteractionResponded:
            await interaction.followup.send("❌ 處理請求時發生錯誤，請稍後再試。", ephemeral=True)


class KeywordCog(commands.Cog):
    """關鍵詞觸發系統 Cog"""

    def __init__(self, bot: commands.Bot) -> None:
        """初始化 Cog

        Args:
            bot: Discord Bot 實例
        """
        self.bot = bot
        self.keywords_file = "private/server_keywords.json"
        self.keywords: dict[str, dict[str, str]] = {}
        self.load_keywords()

        # 添加 Message Context Menu（通用刪除功能）
        self.ctx_menu = app_commands.ContextMenu(
            name="刪除此訊息", callback=self.delete_bot_message
        )
        self.bot.tree.add_command(self.ctx_menu)

    def load_keywords(self) -> None:
        """從 JSON 文件載入關鍵詞配置"""
        try:
            if pathlib.Path(self.keywords_file).exists():
                with pathlib.Path(self.keywords_file).open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 過濾掉註釋和格式說明
                    self.keywords = {k: v for k, v in data.items() if not k.startswith("_")}
                logger.info(f"✅ 已載入 {len(self.keywords)} 個伺服器的關鍵詞配置")
            else:
                self.keywords = {}
                self.save_keywords()
                logger.info("✅ 創建新的關鍵詞配置文件")
        except Exception as e:
            logger.error(f"❌ 載入關鍵詞配置失敗: {e}", exc_info=True)
            self.keywords = {}

    def save_keywords(self) -> None:
        """保存關鍵詞配置到 JSON 文件"""
        try:
            # 添加註釋和格式說明
            data = {
                "_comment": "伺服器關鍵詞配置文件",
                "_format": {"guild_id": {"keyword": "response"}},
                **self.keywords,
            }

            with pathlib.Path(self.keywords_file).open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("💾 已保存關鍵詞配置")
        except Exception as e:
            logger.error(f"❌ 保存關鍵詞配置失敗: {e}", exc_info=True)

    def is_admin(self, interaction: Interaction) -> bool:
        """檢查用戶是否為管理員

        管理員定義：
        1. 伺服器擁有者
        2. 擁有「管理員」權限的成員

        Args:
            interaction: Discord 互動對象

        Returns:
            是否為管理員
        """
        if not interaction.guild:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        # 檢查是否為伺服器擁有者
        if interaction.guild.owner_id == member.id:
            return True

        # 檢查是否有管理員權限
        return bool(member.guild_permissions.administrator)

    def get_guild_keywords(self, guild_id: int) -> dict[str, str]:
        """獲取指定伺服器的關鍵詞

        Args:
            guild_id: 伺服器 ID

        Returns:
            關鍵詞字典
        """
        guild_id_str = str(guild_id)
        if guild_id_str not in self.keywords:
            self.keywords[guild_id_str] = {}
        return self.keywords[guild_id_str]

    async def delete_bot_message(self, interaction: Interaction, message: discord.Message) -> None:
        """刪除機器人訊息（Message Context Menu 回調）

        支持兩種類型的訊息：
        1. 關鍵詞觸發的回覆（使用 reply）
        2. 指令觸發的訊息（使用訊息追蹤器）

        Args:
            interaction: Discord 互動對象
            message: 被右鍵點擊的訊息
        """
        from utils.message_tracker import get_message_tracker

        # 檢查是否為機器人的訊息
        if message.author.id != self.bot.user.id:
            await interaction.response.send_message(
                "❌ 此功能只能用於刪除機器人的訊息！", ephemeral=True
            )
            return

        trigger_user_id: int | None = None
        message_type = "unknown"
        original_content = ""

        # 方式 1：檢查是否為回覆（reply）- 用於關鍵詞
        if message.reference and message.reference.message_id:
            try:
                original_message = await message.channel.fetch_message(message.reference.message_id)
                trigger_user_id = original_message.author.id
                message_type = "keyword"
                original_content = original_message.content
            except discord.NotFound:
                pass  # 原始訊息不存在，嘗試其他方式
            except Exception as e:
                logger.error(f"❌ 獲取原始訊息時發生錯誤: {e}", exc_info=True)

        # 方式 2：檢查訊息追蹤器 - 用於指令（如 copypasta）
        if trigger_user_id is None:
            tracker = get_message_tracker()
            trigger_user_id = tracker.get_trigger_user(message.id)
            if trigger_user_id is not None:
                message_type = "command"

        # 如果無法確定觸發者
        if trigger_user_id is None:
            await interaction.response.send_message(
                "❌ 無法確定此訊息的觸發者。\n此功能僅支援關鍵詞回覆和指令觸發的訊息。",
                ephemeral=True,
            )
            return

        # 檢查權限：觸發者或管理員
        is_trigger_user = interaction.user.id == trigger_user_id
        is_admin = self.is_admin(interaction)

        if not is_trigger_user and not is_admin:
            await interaction.response.send_message(
                "❌ 只有觸發此訊息的用戶或管理員才能刪除！", ephemeral=True
            )
            return

        # 創建確認視圖
        view = DeleteConfirmView(message, interaction.user)

        # 根據訊息類型顯示不同的確認訊息
        if message_type == "keyword":
            confirm_text = (
                f"⚠️ 確定要刪除這條訊息嗎？\n\n"
                f"**原始訊息：** {original_content[:50]}{'...' if len(original_content) > 50 else ''}\n"
                f"**回覆內容：** {message.content[:50]}{'...' if len(message.content) > 50 else ''}"
            )
        else:  # command
            confirm_text = (
                f"⚠️ 確定要刪除這條訊息嗎？\n\n"
                f"**訊息內容：** {message.content[:100]}{'...' if len(message.content) > 100 else ''}"
            )

        # 發送確認訊息
        await interaction.response.send_message(confirm_text, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """監聽訊息事件，檢查是否匹配關鍵詞

        Args:
            message: Discord 訊息對象
        """
        # 忽略機器人自己的訊息
        if message.author.bot:
            return

        # 忽略私訊
        if not message.guild:
            return

        # 獲取該伺服器的關鍵詞
        guild_keywords = self.get_guild_keywords(message.guild.id)

        # 檢查訊息內容是否完全匹配關鍵詞
        content = message.content.strip()
        if content in guild_keywords:
            response = guild_keywords[content]
            try:
                # 使用 reply 回覆，這樣可以追溯到觸發者
                await message.reply(response, mention_author=False)
                logger.debug(
                    f"🔑 觸發關鍵詞 '{content}' 在伺服器 {message.guild.name} ({message.guild.id})"
                )
            except Exception as e:
                logger.error(f"❌ 發送關鍵詞回覆失敗: {e}", exc_info=True)

    # Slash Commands 群組
    keyword_group = app_commands.Group(name="keyword", description="關鍵詞管理命令（僅管理員）")

    @keyword_group.command(name="add", description="添加新的關鍵詞觸發（使用彈出式表單）")
    async def keyword_add(self, interaction: Interaction) -> None:
        """添加新的關鍵詞（使用 Modal）

        Args:
            interaction: Discord 互動對象
        """
        # 檢查權限
        if not self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ 只有伺服器管理員才能使用此命令！", ephemeral=True
            )
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令只能在伺服器中使用！", ephemeral=True)
            return

        # 顯示 Modal
        modal = KeywordAddModal(self)
        await interaction.response.send_modal(modal)

    @keyword_group.command(name="list", description="列出所有關鍵詞")
    async def keyword_list(self, interaction: Interaction) -> None:
        """列出當前伺服器的所有關鍵詞

        Args:
            interaction: Discord 互動對象
        """
        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令只能在伺服器中使用！", ephemeral=True)
            return

        # 獲取伺服器關鍵詞
        guild_keywords = self.get_guild_keywords(interaction.guild.id)

        if not guild_keywords:
            await interaction.response.send_message(
                "📝 此伺服器還沒有設定任何關鍵詞。\n管理員可以使用 `/keyword add` 添加關鍵詞。",
                ephemeral=True,
            )
            return

        # 創建 Embed 顯示關鍵詞列表
        embed = discord.Embed(
            title=f"📝 {interaction.guild.name} 的關鍵詞列表",
            description=f"共有 {len(guild_keywords)} 個關鍵詞",
            color=discord.Color.blue(),
        )

        # 添加關鍵詞字段（最多顯示 25 個）
        for _i, (keyword, response) in enumerate(list(guild_keywords.items())[:25]):
            # 截斷過長的回覆
            display_response = response if len(response) <= 100 else response[:97] + "..."
            embed.add_field(name=f"🔑 {keyword}", value=display_response, inline=False)

        if len(guild_keywords) > 25:
            embed.set_footer(text=f"僅顯示前 25 個關鍵詞，共有 {len(guild_keywords)} 個")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_unload(self) -> None:
        """Cog 卸載時的清理工作"""
        # 移除 Context Menu
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        logger.info("✅ KeywordCog Context Menu 已移除")


async def setup(bot: commands.Bot) -> None:
    """載入 Cog

    Args:
        bot: Discord Bot 實例
    """
    await bot.add_cog(KeywordCog(bot))
    logger.info("✅ KeywordCog 已載入")
