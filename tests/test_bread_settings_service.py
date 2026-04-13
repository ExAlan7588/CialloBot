from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bread.services.settings_service import set_guild_item_name
from utils.exceptions import BusinessError


class BreadSettingsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_guild_item_name_maps_uninitialized_pool_to_feature_disabled(self) -> None:
        with (
            patch(
                "bread.services.settings_service.get_or_create_guild_config",
                AsyncMock(return_value={"item_name": "面包"}),
            ),
            patch(
                "bread.services.settings_service.get_pool",
                side_effect=RuntimeError("PostgreSQL 連線池尚未初始化。"),
            ),
        ):
            with self.assertRaises(BusinessError) as context:
                await set_guild_item_name(guild_id=123, item_name="可頌")

        self.assertEqual(context.exception.author_name, "功能未啟用")
        self.assertEqual(
            context.exception.description,
            "目前尚未配置 PostgreSQL，Bread 系統尚未啟用。",
        )


if __name__ == "__main__":
    unittest.main()
