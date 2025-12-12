"""osu! Discord Bot 主程式

這是一個 Discord 機器人，提供 osu! 遊戲相關的功能。
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from loguru import logger

from private import config
from utils.osu_api import OsuAPI
from utils.startup import setup_logging, wrap_task_factory

if TYPE_CHECKING:
    pass


class OsuBot(commands.Bot):
    """自定義的 Discord Bot 類別。

    擴展了 discord.py 的 Bot 類別，添加了自定義的初始化和錯誤處理。
    """

    def __init__(self, **options: Any) -> None:
        """初始化 Bot。

        Args:
            **options: 傳遞給 discord.py Bot 的選項
        """
        super().__init__(**options)
        self.osu_api_client: OsuAPI | None = None

    async def setup_hook(self) -> None:
        """Bot 的異步設置鉤子。

        在 Bot 連接到 Discord 之前執行，用於初始化各種服務。
        """
        logger.info("== 開始異步設置 ==")

        # 初始化 OsuAPI 客戶端
        try:
            self.osu_api_client = OsuAPI(
                client_id=config.OSU_API_V2_CLIENT_ID,
                client_secret=config.OSU_API_V2_CLIENT_SECRET,
                api_v1_key=config.OSU_API_V1_KEY,
            )
            await self.osu_api_client.setup()
            logger.info("✅ OsuAPI 客戶端已初始化")
        except Exception as e:
            logger.error(f"❌ OsuAPI 客戶端初始化失敗: {e}", exc_info=True)
            raise

        # 載入所有 Cogs
        await self._load_all_cogs()

        # 同步應用程式命令（Slash Commands）
        try:
            # 檢查是否為測試模式
            env_mode = getattr(config, "ENV_MODE", "").lower()

            if env_mode == "test":
                # 測試模式：只同步到測試伺服器
                TEST_GUILD_ID = 1449019047822889012
                guild = discord.Object(id=TEST_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(
                    "✅ [測試模式] 已同步 {count} 個應用程式命令到測試伺服器", count=len(synced)
                )
            else:
                # 正式模式：全域同步（所有伺服器）
                synced = await self.tree.sync()
                logger.info("✅ 已全域同步 {count} 個應用程式命令", count=len(synced))

        except Exception as e:
            logger.error(f"❌ 同步應用程式命令失敗: {e}", exc_info=True)

        logger.info("✅ 異步設置完成")

    async def _load_all_cogs(self) -> None:
        """載入所有 Cog 模組。"""
        import os

        logger.info("== 開始載入所有 Cog 模組 ==")

        if not os.path.exists("./cogs"):
            os.makedirs("./cogs")
            logger.warning("⚠️ cogs 資料夾不存在，已自動創建。")
            return

        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = filename[:-3]
                try:
                    await self.load_extension(f"cogs.{cog_name}")
                    logger.info("✅ 已成功載入 Cog: {cog_name}", cog_name=cog_name)
                except commands.ExtensionAlreadyLoaded:
                    logger.warning("⚠️ Cog {cog_name} 已經載入", cog_name=cog_name)
                except Exception as e:
                    logger.error(f"❌ 載入 Cog {cog_name} 失敗: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """當 Bot 準備就緒時觸發。"""
        logger.info("== Bot Ready ==")
        logger.info(
            "Logged in as: {user_name} (ID: {user_id})",
            user_name=self.user.name if self.user else "Unknown",
            user_id=self.user.id if self.user else "Unknown",
        )
        logger.info("Discord.py Version: {version}", version=discord.__version__)

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        """處理事件中的未捕獲錯誤。

        Args:
            event_method: 發生錯誤的事件方法名稱
            *args: 事件參數
            **kwargs: 事件關鍵字參數
        """
        logger.exception(f"在事件 '{event_method}' 中發生未捕獲的異常")

    async def close(self) -> None:
        """關閉 Bot 並清理資源。"""
        logger.info("機器人正在關閉...")

        # 關閉 OsuAPI 客戶端
        if self.osu_api_client:
            try:
                await self.osu_api_client.close()
                logger.info("✅ OsuAPI 客戶端已關閉")
            except Exception as e:
                logger.error(f"❌ 關閉 OsuAPI 客戶端時發生錯誤: {e}", exc_info=True)

        await super().close()
        logger.info("機器人關閉完成")


async def main() -> None:
    """主啟動函數。"""
    # 設定日誌系統
    setup_logging(log_file="logs/bot.log", log_level="INFO")

    # 檢查 Discord Token
    token = config.DISCORD_BOT_TOKEN
    if not token:
        logger.critical("❌ 錯誤：找不到 DISCORD_BOT_TOKEN。機器人無法啟動。")
        sys.exit(1)

    # 設定 Intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # 創建 Bot 實例
    bot = OsuBot(
        command_prefix="!",
        intents=intents,
        log_handler=None,  # 禁用 discord.py 的預設日誌處理器
    )

    try:
        logger.info("正在啟動機器人...")

        # 包裝任務工廠以捕獲背景任務的異常
        wrap_task_factory()

        # 啟動 Bot
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("收到鍵盤中斷信號，正在優雅地關閉機器人...")
    except Exception:
        logger.exception("啟動機器人時發生未預期的錯誤")
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被強制終止。")
