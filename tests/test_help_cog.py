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
        group = app_commands.Group(name="bread", description="Bread 商店玩法")

        @group.command(name="buy", description="購買 Bread 物品")
        async def _buy(_interaction):  # pragma: no cover - discord callback placeholder
            return None

        @group.command(name="rank", description="查看 Bread 排行榜")
        async def _rank(_interaction):  # pragma: no cover - discord callback placeholder
            return None

        flattened = list(_flatten_app_commands([group]))

        self.assertIn(("bread buy", "bread buy", "購買 Bread 物品"), flattened)
        self.assertIn(("bread rank", "bread rank", "查看 Bread 排行榜"), flattened)


if __name__ == "__main__":
    unittest.main()
