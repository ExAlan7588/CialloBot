from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from bread.services.gameplay_utils import (
    build_feature_disabled_error,
    ensure_guild_supported,
    format_remaining_time,
    raise_cooldown_error,
    resolve_state_change_conflict,
)
from utils.exceptions import BusinessError


class BreadGameplayUtilsTests(unittest.TestCase):
    def test_ensure_guild_supported_returns_guild_id(self) -> None:
        self.assertEqual(ensure_guild_supported(123), 123)

    def test_ensure_guild_supported_rejects_dm(self) -> None:
        with self.assertRaises(BusinessError) as context:
            ensure_guild_supported(None)

        self.assertEqual(context.exception.author_name, "無法使用")
        self.assertEqual(context.exception.description, "Bread 功能目前只能在伺服器內使用。")

    def test_build_feature_disabled_error_uses_canonical_message(self) -> None:
        error = build_feature_disabled_error()
        self.assertEqual(error.author_name, "功能未啟用")
        self.assertEqual(error.description, "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。")

    def test_format_remaining_time_rounds_down_to_seconds(self) -> None:
        delta = timedelta(minutes=1, seconds=9, milliseconds=999)
        self.assertEqual(format_remaining_time(delta), "1分9秒")

    def test_raise_cooldown_error_uses_shared_message_shape(self) -> None:
        now = datetime(2026, 4, 13, 9, 0, tzinfo=UTC)
        cooldown_until = now + timedelta(seconds=75)

        with self.assertRaises(BusinessError) as context:
            raise_cooldown_error(
                action_name="買",
                item_name="可頌",
                cooldown_until=cooldown_until,
                now=now,
            )

        self.assertEqual(context.exception.author_name, "冷卻中")
        self.assertEqual(context.exception.description, "無法買可頌，還有1分15秒")

    def test_resolve_state_change_conflict_returns_retry_when_missing_latest_row(self) -> None:
        now = datetime(2026, 4, 13, 9, 0, tzinfo=UTC)

        with self.assertRaises(BusinessError) as context:
            resolve_state_change_conflict(
                item_name="可頌",
                action_name="送",
                latest_row=None,
                cooldown_key="give_cooldown_until",
                now=now,
            )

        self.assertEqual(context.exception.author_name, "請重試")
        self.assertEqual(context.exception.description, "Bread 狀態剛剛被更新，請再試一次。")

    def test_resolve_state_change_conflict_prefers_cooldown_error(self) -> None:
        now = datetime(2026, 4, 13, 9, 0, tzinfo=UTC)
        latest_row = {"rob_cooldown_until": now + timedelta(seconds=30)}

        with self.assertRaises(BusinessError) as context:
            resolve_state_change_conflict(
                item_name="可頌",
                action_name="搶",
                latest_row=latest_row,
                cooldown_key="rob_cooldown_until",
                now=now,
            )

        self.assertEqual(context.exception.author_name, "冷卻中")
        self.assertEqual(context.exception.description, "無法搶可頌，還有30秒")


if __name__ == "__main__":
    unittest.main()
