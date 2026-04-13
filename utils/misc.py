"""雜項工具函數模組

包含各種輔助函數，如錯誤處理、異常捕獲等。
"""

from __future__ import annotations

from loguru import logger


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

    return bool(isinstance(error, asyncio.CancelledError))


def capture_exception(
    exception: Exception,
    *,
    context: str | None = None,
    level: str = "error",
) -> None:
    """捕獲並記錄異常。

    這個函數可以用於集中處理異常，未來可以擴展為
    發送到錯誤追蹤服務（如 Sentry）。

    Args:
        exception: 要捕獲的異常
    """
    if should_ignore_error(exception):
        return

    normalized_level = level.upper()
    message_prefix = f"{context}: " if context else ""
    message = f"{message_prefix}{type(exception).__name__}: {exception}"

    try:
        logger.opt(exception=exception).log(normalized_level, message)
    except ValueError:
        logger.opt(exception=exception).error(message)
