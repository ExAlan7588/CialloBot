from __future__ import annotations

from typing import Any


class BusinessError(Exception):
    def __init__(self, description: str, *, author_name: str = "操作失敗") -> None:
        super().__init__(description)
        self.author_name = author_name
        self.description = description


class ConfigurationError(Exception):
    pass


class DatabaseOperationError(BusinessError):
    def __init__(
        self,
        description: str = "資料庫操作失敗。",
        *,
        original_exception: Exception | None = None,
    ) -> None:
        super().__init__(description, author_name="資料庫操作失敗")
        self.original_exception = original_exception


class OnCooldownError(BusinessError):
    def __init__(
        self,
        description: str,
        *,
        retry_after: float | None = None,
        show_user: bool = True,
    ) -> None:
        super().__init__(description, author_name="冷卻中")
        self.retry_after = retry_after
        self.show_user = show_user


class PermissionDeniedError(BusinessError):
    def __init__(self, description: str = "你沒有權限執行這個操作。") -> None:
        super().__init__(description, author_name="權限不足")


class InvalidQuantityError(BusinessError):
    def __init__(self, quantity: Any | None = None) -> None:
        description = f"數量必須是正整數，收到: {quantity}"
        super().__init__(description, author_name="數量無效")
        self.quantity = quantity
