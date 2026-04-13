from __future__ import annotations

import unittest

from bread.services.record_service import get_record_page
from utils.exceptions import BusinessError


class BreadRecordServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_record_page_rejects_non_positive_page(self) -> None:
        with self.assertRaises(BusinessError) as context:
            await get_record_page(
                guild_id=123,
                user_id=456,
                fallback_nickname="DiscordActor",
                page=0,
            )

        self.assertEqual(context.exception.author_name, "頁碼錯誤")
        self.assertEqual(context.exception.description, "頁碼必須大於 0。")


if __name__ == "__main__":
    unittest.main()
