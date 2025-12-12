"""日誌攔截器模組

此模組提供 InterceptHandler，用於將 Python 標準 logging 模組的日誌
重定向到 loguru，實現統一的日誌管理。
"""

from __future__ import annotations

import inspect
import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    """攔截標準 logging 模組的日誌並重定向到 loguru。
    
    這個處理器會捕獲所有通過標準 logging 模組記錄的日誌
    （包括第三方庫如 discord.py），並將它們轉發到 loguru。
    """

    def emit(self, record: logging.LogRecord) -> None:
        """處理日誌記錄。
        
        Args:
            record: 標準 logging 的日誌記錄
        """
        # 獲取對應的 loguru 日誌等級
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到調用者的堆疊幀
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        # 使用 loguru 記錄日誌
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
