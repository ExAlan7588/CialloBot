from __future__ import annotations

from discord import app_commands

from cogs.help_cog import _flatten_app_commands


def test_flatten_group_commands() -> None:
    group = app_commands.Group(name="keyword", description="關鍵詞管理命令")

    @group.command(name="add", description="添加新的關鍵詞觸發")
    async def _add(_interaction):  # pragma: no cover - discord callback placeholder
        return None

    @group.command(name="list", description="列出所有關鍵詞")
    async def _list(_interaction):  # pragma: no cover - discord callback placeholder
        return None

    flattened = list(_flatten_app_commands([group]))

    assert ("keyword add", "keyword add", "添加新的關鍵詞觸發") in flattened
    assert ("keyword list", "keyword list", "列出所有關鍵詞") in flattened
