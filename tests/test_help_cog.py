from __future__ import annotations

import sys
import types
import unittest

from discord import app_commands

stub_config = types.ModuleType("private.config")
setattr(stub_config, "DEFAULT_LANGUAGE", "en")
setattr(stub_config, "SUPPORTED_LANGUAGES", ["en", "zh_TW"])
sys.modules["private.config"] = stub_config

from cogs.help_cog import _flatten_app_commands


class HelpCogTests(unittest.TestCase):
    def test_flatten_group_commands(self) -> None:
        group = app_commands.Group(name="keyword", description="關鍵詞管理命令")

        @group.command(name="add", description="添加新的關鍵詞觸發")
        async def _add(_interaction):  # pragma: no cover - discord callback placeholder
            return None

        @group.command(name="list", description="列出所有關鍵詞")
        async def _list(_interaction):  # pragma: no cover - discord callback placeholder
            return None

        flattened = list(_flatten_app_commands([group]))

        self.assertIn(("keyword add", "keyword add", "添加新的關鍵詞觸發"), flattened)
        self.assertIn(("keyword list", "keyword list", "列出所有關鍵詞"), flattened)


if __name__ == "__main__":
    unittest.main()
