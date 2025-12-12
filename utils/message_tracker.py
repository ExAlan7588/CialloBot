"""訊息追蹤器

此模組提供一個全局的訊息追蹤系統，用於記錄機器人發送的訊息及其觸發者。
這使得 Context Menu 可以驗證刪除權限。
"""

from __future__ import annotations

from loguru import logger


class MessageTracker:
    """訊息追蹤器

    記錄機器人發送的訊息及其觸發者，用於權限驗證。

    特點：
    - 內存存儲（重啟後清空）
    - 自動清理舊記錄（防止內存洩漏）
    - 線程安全
    """

    def __init__(self, max_size: int = 10000) -> None:
        """初始化訊息追蹤器

        Args:
            max_size: 最大記錄數量，超過後自動清理最舊的記錄
        """
        self._messages: dict[int, int] = {}  # {message_id: user_id}
        self.max_size = max_size

    def track_message(self, message_id: int, user_id: int) -> None:
        """記錄訊息及其觸發者

        Args:
            message_id: 訊息 ID
            user_id: 觸發者用戶 ID
        """
        # 如果超過最大容量，清理最舊的 10% 記錄
        if len(self._messages) >= self.max_size:
            self._cleanup_old_messages()

        self._messages[message_id] = user_id
        logger.debug(f"📝 追蹤訊息: message_id={message_id}, user_id={user_id}")

    def get_trigger_user(self, message_id: int) -> int | None:
        """獲取訊息的觸發者

        Args:
            message_id: 訊息 ID

        Returns:
            觸發者用戶 ID，如果找不到則返回 None
        """
        return self._messages.get(message_id)

    def remove_message(self, message_id: int) -> None:
        """移除訊息記錄

        Args:
            message_id: 訊息 ID
        """
        if message_id in self._messages:
            del self._messages[message_id]
            logger.debug(f"🗑️ 移除訊息追蹤: message_id={message_id}")

    def _cleanup_old_messages(self) -> None:
        """清理最舊的 10% 記錄"""
        cleanup_count = max(1, self.max_size // 10)

        # 獲取最舊的記錄（字典保持插入順序）
        old_messages = list(self._messages.keys())[:cleanup_count]

        for message_id in old_messages:
            del self._messages[message_id]

        logger.info(
            f"🧹 清理了 {cleanup_count} 條舊訊息記錄 (剩餘: {len(self._messages)})"
        )

    def get_stats(self) -> dict[str, int]:
        """獲取統計信息

        Returns:
            統計信息字典
        """
        return {
            "total_tracked": len(self._messages),
            "max_size": self.max_size,
            "usage_percent": int(len(self._messages) / self.max_size * 100),
        }

    def clear(self) -> None:
        """清空所有記錄"""
        count = len(self._messages)
        self._messages.clear()
        logger.info(f"🧹 清空了所有訊息追蹤記錄 (共 {count} 條)")


# 全局訊息追蹤器實例
_global_tracker: MessageTracker | None = None


def get_message_tracker() -> MessageTracker:
    """獲取全局訊息追蹤器實例

    Returns:
        全局訊息追蹤器
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = MessageTracker()
        logger.info("✅ 初始化全局訊息追蹤器")
    return _global_tracker
