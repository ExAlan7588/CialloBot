from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from discord.ext import commands

from private import config
from bot import MISSING_DISCORD_TOKEN_MESSAGE, OsuBot, get_discord_token


class StubOsuApi:
    def __init__(
        self, *, setup_error: Exception | None = None, close_error: Exception | None = None
    ) -> None:
        self._setup_error = setup_error
        self._close_error = close_error
        self.setup_called = False
        self.close_called = False

    async def setup(self) -> None:
        self.setup_called = True
        if self._setup_error is not None:
            raise self._setup_error

    async def close(self) -> None:
        self.close_called = True
        if self._close_error is not None:
            raise self._close_error


def test_command_not_found_is_ignored_without_default_error_logging() -> None:
    asyncio.run(_assert_command_not_found_is_ignored())


async def _assert_command_not_found_is_ignored() -> None:
    bot = OsuBot(command_prefix="!", intents=None)
    ctx = Mock()
    error = commands.CommandNotFound('Command "!token" is not found')

    try:
        with patch.object(
            commands.Bot,
            "on_command_error",
            new=AsyncMock(side_effect=AssertionError("default handler should not run")),
        ):
            await bot.on_command_error(ctx, error)
    finally:
        await bot.close()


def test_other_command_errors_use_default_error_logging() -> None:
    asyncio.run(_assert_other_command_errors_use_default_handler())


async def _assert_other_command_errors_use_default_handler() -> None:
    bot = OsuBot(command_prefix="!", intents=None)
    ctx = Mock()
    error = commands.CommandInvokeError(RuntimeError("boom"))

    try:
        with patch.object(commands.Bot, "on_command_error", new=AsyncMock()) as handler:
            await bot.on_command_error(ctx, error)
    finally:
        await bot.close()

    handler.assert_awaited_once_with(ctx, error)


def test_missing_token_raises_explicit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DISCORD_BOT_TOKEN", "")

    with pytest.raises(RuntimeError, match=MISSING_DISCORD_TOKEN_MESSAGE):
        get_discord_token()


def test_missing_cogs_directory_raises_file_not_found() -> None:
    asyncio.run(_assert_missing_cogs_directory_raises())


async def _assert_missing_cogs_directory_raises() -> None:
    bot = OsuBot(command_prefix="!", intents=None, cogs_dir=Path("missing-cogs"))

    try:
        with pytest.raises(FileNotFoundError):
            bot._discover_cog_names()
    finally:
        await bot.close()


def test_discover_cog_names_returns_only_extension_modules(tmp_path: Path) -> None:
    asyncio.run(_assert_discover_cog_names_returns_only_extension_modules(tmp_path))


async def _assert_discover_cog_names_returns_only_extension_modules(cogs_dir: Path) -> None:
    (cogs_dir / "real_cog.py").write_text("async def setup(bot):\n    pass\n")
    (cogs_dir / "helper.py").write_text("class Helper:\n    pass\n")
    (cogs_dir / "_private_cog.py").write_text("async def setup(bot):\n    pass\n")
    bot = OsuBot(command_prefix="!", intents=None, cogs_dir=cogs_dir)

    try:
        assert bot._discover_cog_names() == ["real_cog"]
    finally:
        await bot.close()


def test_setup_hook_propagates_api_setup_failure() -> None:
    asyncio.run(_assert_setup_hook_propagates_api_setup_failure())


async def _assert_setup_hook_propagates_api_setup_failure() -> None:
    api = StubOsuApi(setup_error=RuntimeError("setup failed"))
    bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api)

    try:
        with pytest.raises(RuntimeError, match="setup failed"):
            await bot.setup_hook()
    finally:
        await bot.close()

    assert api.setup_called


def test_setup_hook_propagates_cog_load_failure(tmp_path: Path) -> None:
    asyncio.run(_assert_setup_hook_propagates_cog_load_failure(tmp_path))


async def _assert_setup_hook_propagates_cog_load_failure(cogs_dir: Path) -> None:
    api = StubOsuApi()
    (cogs_dir / "broken_cog.py").write_text("async def setup(bot):\n    pass\n")
    bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api, cogs_dir=cogs_dir)

    try:
        with patch.object(
            bot, "load_extension", new=AsyncMock(side_effect=RuntimeError("load failed"))
        ):
            with pytest.raises(RuntimeError, match="load failed"):
                await bot.setup_hook()
    finally:
        await bot.close()

    assert api.setup_called


def test_setup_hook_propagates_command_sync_failure(tmp_path: Path) -> None:
    asyncio.run(_assert_setup_hook_propagates_command_sync_failure(tmp_path))


async def _assert_setup_hook_propagates_command_sync_failure(cogs_dir: Path) -> None:
    api = StubOsuApi()
    bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api, cogs_dir=cogs_dir)

    try:
        with patch.object(bot.tree, "sync", new=AsyncMock(side_effect=RuntimeError("sync failed"))):
            with pytest.raises(RuntimeError, match="sync failed"):
                await bot.setup_hook()
    finally:
        await bot.close()

    assert api.setup_called


def test_close_propagates_api_close_failure_after_bot_close() -> None:
    asyncio.run(_assert_close_propagates_api_close_failure_after_bot_close())


async def _assert_close_propagates_api_close_failure_after_bot_close() -> None:
    api = StubOsuApi(close_error=RuntimeError("close failed"))
    bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api)
    bot.osu_api_client = api

    with pytest.raises(RuntimeError, match="close failed"):
        await bot.close()

    assert api.close_called
    assert bot.is_closed()
