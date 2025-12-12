"""雜項工具函數模組

包含各種輔助函數，如錯誤處理、異常捕獲等。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from typing import Any


def should_ignore_error(error: Exception) -> bool:
    """判斷是否應該忽略特定錯誤。

    某些錯誤是預期的或不重要的，可以被忽略而不記錄。

    Args:
        error: 要檢查的異常

    Returns:
        如果應該忽略該錯誤則返回 True
    """
    # 可以在這裡添加需要忽略的錯誤類型
    # 例如：取消的任務、連接超時等
    import asyncio

    if isinstance(error, asyncio.CancelledError):
        return True

    return False


def capture_exception(exception: Exception) -> None:
    """捕獲並記錄異常。

    這個函數可以用於集中處理異常，未來可以擴展為
    發送到錯誤追蹤服務（如 Sentry）。

    Args:
        exception: 要捕獲的異常
    """
    if not should_ignore_error(exception):
        logger.exception(f"捕獲到未處理的異常: {exception}")
