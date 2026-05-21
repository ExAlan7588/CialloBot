"""雜項工具函數模組。"""

from __future__ import annotations

import asyncio


def should_ignore_error(error: Exception) -> bool:
    """判斷是否應該忽略特定錯誤。

    某些錯誤是預期的或不重要的，可以被忽略而不記錄。

    Args:
        error: 要檢查的異常

    Returns:
        如果應該忽略該錯誤則返回 True
    """
    return bool(isinstance(error, asyncio.CancelledError))
