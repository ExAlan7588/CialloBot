"""啟動工具模組

包含日誌系統初始化和 asyncio 任務包裝器等啟動相關的工具函數。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.log_intercept import InterceptHandler
from utils.misc import should_ignore_error

if TYPE_CHECKING:
    from collections.abc import Coroutine


# 全域任務集合，用於追蹤所有背景任務
_tasks_set: set[asyncio.Task[Any] | asyncio.Future[Any]] = set()


def wrap_task_factory() -> None:
    """包裝 asyncio 的任務工廠，為每個任務添加全域錯誤處理器。

    這確保了通過 `asyncio.create_task()` 創建的背景任務
    如果發生未捕獲的異常，能夠被記錄下來，而不是悄無聲息地失敗。
    """
    loop = asyncio.get_running_loop()
    original_factory = loop.get_task_factory()

    async def coro_wrapper(
        coro: Coroutine[Any, Any, Any], name: str | None = None
    ) -> Any:
        """包裝協程，添加異常處理。"""
        try:
            return await coro
        except Exception as e:
            if not should_ignore_error(e):
                task_name = name or getattr(coro, "__name__", str(coro))
                logger.exception(f"任務 '{task_name}' 中發生未捕獲的異常: {e}")
            raise

    def new_factory(
        loop: asyncio.AbstractEventLoop,
        coro: Coroutine[Any, Any, Any],
        **kwargs: Any,
    ) -> asyncio.Task[Any]:
        """新的任務工廠函數。"""
        task_name = kwargs.get("name")
        wrapped_coro = coro_wrapper(coro, name=task_name)

        if original_factory:
            task = original_factory(loop, wrapped_coro, **kwargs)
        else:
            task = asyncio.Task(wrapped_coro, loop=loop, **kwargs)

        # 追蹤任務，防止被垃圾回收
        _tasks_set.add(task)
        task.add_done_callback(_tasks_set.discard)

        return task  # type: ignore[return-value]

    loop.set_task_factory(new_factory)


def setup_logging(log_file: str = "logs/bot.log", log_level: str = "INFO") -> None:
    """設定 loguru 日誌系統。

    此函數會：
    1. 移除 loguru 的預設處理器
    2. 添加控制台輸出（彩色）
    3. 添加文件輸出（自動輪轉）
    4. 攔截所有標準 logging 模組的日誌（包括 discord.py）

    Args:
        log_file: 日誌文件路徑，預設為 "logs/bot.log"
        log_level: 日誌等級，預設為 "INFO"
    """
    # 移除預設的 loguru 處理器
    logger.remove()

    # 添加控制台輸出（彩色、格式化）
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # 攔截所有標準 logging 模組的日誌
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

    # 添加文件輸出（自動輪轉、保留）
    logger.add(
        log_file,
        rotation="10 MB",  # 每 10 MB 輪轉一次
        retention="7 days",  # 保留 7 天
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
    )

    logger.info("✅ 日誌系統初始化完成。日誌等級: {log_level}", log_level=log_level)
