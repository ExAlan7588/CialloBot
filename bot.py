"""osu! Discord Bot 主程式

這是一個 Discord 機器人，提供 osu! 遊戲相關的功能。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol

import discord
from discord.ext import commands
from loguru import logger

from private import config
from utils.osu_api import OsuAPI
from utils.startup import setup_logging, wrap_task_factory

COGS_DIR = Path(__file__).resolve().parent / "cogs"
COGS_PACKAGE = "cogs"
COMMAND_PREFIX = "!"
LOG_FILE = "logs/bot.log"
LOG_LEVEL = "INFO"
MISSING_DISCORD_TOKEN_MESSAGE = "DISCORD_BOT_TOKEN is required"


class OsuApiClient(Protocol):
    """Minimal osu! API client contract needed by the bot lifecycle."""

    async def setup(self) -> None: ...

    async def close(self) -> None: ...


class OsuApiFactory(Protocol):
    """Factory contract for constructing osu! API clients."""

    def __call__(self) -> OsuApiClient: ...


def create_osu_api_client() -> OsuAPI:
    """Create the production osu! API client from configured credentials."""
    return OsuAPI(
        client_id=config.OSU_API_V2_CLIENT_ID,
        client_secret=config.OSU_API_V2_CLIENT_SECRET,
        api_v1_key=config.OSU_API_V1_KEY,
    )


class OsuBot(commands.Bot):
    """自定義的 Discord Bot 類別。

    擴展了 discord.py 的 Bot 類別，添加了自定義的初始化和錯誤處理。
    """

    def __init__(
        self,
        *,
        osu_api_factory: OsuApiFactory = create_osu_api_client,
        cogs_dir: Path = COGS_DIR,
        **options: Any,
    ) -> None:
        """初始化 Bot。

        Args:
            osu_api_factory: osu! API 客戶端工廠。
            cogs_dir: Cog 模組所在目錄。
            **options: 傳遞給 discord.py Bot 的選項
        """
        super().__init__(**options)
        self._osu_api_factory = osu_api_factory
        self._cogs_dir = cogs_dir
        self.osu_api_client: OsuApiClient | None = None

    async def setup_hook(self) -> None:
        """Bot 的異步設置鉤子。

        在 Bot 連接到 Discord 之前執行，用於初始化各種服務。
        """
        logger.info("== 開始異步設置 ==")

        self.osu_api_client = self._osu_api_factory()
        await self.osu_api_client.setup()
        logger.info("✅ OsuAPI 客戶端已初始化")

        await self._load_all_cogs()

        synced = await self.tree.sync()
        logger.info("✅ 已全域同步 {count} 個應用程式命令", count=len(synced))

        logger.info("✅ 異步設置完成")

    async def _load_all_cogs(self) -> None:
        """載入所有 Cog 模組。"""
        logger.info("== 開始載入所有 Cog 模組 ==")

        cog_names = self._discover_cog_names()
        if not cog_names:
            logger.info("沒有可載入的 Cog。")
            return

        for cog_name in cog_names:
            await self.load_extension(f"{COGS_PACKAGE}.{cog_name}")
            logger.info("✅ 已成功載入 Cog: {cog_name}", cog_name=cog_name)

    def _discover_cog_names(self) -> list[str]:
        if not self._cogs_dir.is_dir():
            raise FileNotFoundError(self._cogs_dir)

        return sorted(
            entry.stem
            for entry in self._cogs_dir.iterdir()
            if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("_")
        )

    async def on_ready(self) -> None:
        """當 Bot 準備就緒時觸發。"""
        logger.info("== Bot Ready ==")
        logger.info(
            "Logged in as: {user_name} (ID: {user_id})",
            user_name=self.user.name if self.user else "Unknown",
            user_id=self.user.id if self.user else "Unknown",
        )
        logger.info("Discord.py Version: {version}", version=discord.__version__)

    async def on_error(self, event_method: str, *_args: Any, **_kwargs: Any) -> None:
        """處理事件中的未捕獲錯誤。

        Args:
            event_method: 發生錯誤的事件方法名稱
            *args: 事件參數
            **kwargs: 事件關鍵字參數
        """
        logger.exception(f"在事件 '{event_method}' 中發生未捕獲的異常")

    async def on_command_error(
        self, context: commands.Context[Any], exception: commands.CommandError
    ) -> None:
        """處理文字命令錯誤。

        Bot 主要使用 slash commands；使用者偶爾輸入未知的 ! 指令時，
        discord.py 預設處理器會將 CommandNotFound 記成 ERROR，導致 PM2
        error log 被正常的使用者輸入洗版。未知文字指令直接忽略，其他命令錯誤
        仍交回 discord.py 預設處理器。
        """
        if isinstance(exception, commands.CommandNotFound):
            return

        await super().on_command_error(context, exception)

    async def close(self) -> None:
        """關閉 Bot 並清理資源。"""
        logger.info("機器人正在關閉...")

        try:
            if self.osu_api_client is not None:
                await self.osu_api_client.close()
                logger.info("✅ OsuAPI 客戶端已關閉")
        finally:
            await super().close()
            logger.info("機器人關閉完成")


def create_intents() -> discord.Intents:
    """Create the Discord intents used by the bot."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    return intents


def create_bot() -> OsuBot:
    """Create the production bot instance."""
    return OsuBot(command_prefix=COMMAND_PREFIX, intents=create_intents(), log_handler=None)


def get_discord_token() -> str:
    """Return the configured Discord bot token or fail explicitly."""
    token = config.DISCORD_BOT_TOKEN
    if not token:
        raise RuntimeError(MISSING_DISCORD_TOKEN_MESSAGE)

    return token


async def main() -> None:
    """主啟動函數。"""
    setup_logging(log_file=LOG_FILE, log_level=LOG_LEVEL)
    token = get_discord_token()
    bot = create_bot()

    try:
        logger.info("正在啟動機器人...")
        wrap_task_factory()
        await bot.start(token)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被強制終止。")
