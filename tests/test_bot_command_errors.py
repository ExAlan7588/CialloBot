from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock, patch

from discord.ext import commands

stub_config = types.ModuleType("private.config")
setattr(stub_config, "DISCORD_BOT_TOKEN", "dummy-token")
setattr(stub_config, "OSU_API_V2_CLIENT_ID", "dummy-client-id")
setattr(stub_config, "OSU_API_V2_CLIENT_SECRET", "dummy-client-secret")
setattr(stub_config, "OSU_API_V1_KEY", "dummy-api-v1-key")
sys.modules["private.config"] = stub_config

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


class BotCommandErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bot = OsuBot(command_prefix="!", intents=None)

    async def asyncTearDown(self) -> None:
        await self.bot.close()

    async def test_command_not_found_is_ignored_without_default_error_logging(self) -> None:
        ctx = Mock()
        error = commands.CommandNotFound('Command "!token" is not found')

        with patch.object(
            commands.Bot,
            "on_command_error",
            new=AsyncMock(side_effect=AssertionError("default handler should not run")),
        ):
            await self.bot.on_command_error(ctx, error)

    async def test_other_command_errors_use_default_error_logging(self) -> None:
        ctx = Mock()
        error = commands.CommandInvokeError(RuntimeError("boom"))

        with patch.object(commands.Bot, "on_command_error", new=AsyncMock()) as handler:
            await self.bot.on_command_error(ctx, error)

        handler.assert_awaited_once_with(ctx, error)


class BotLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_raises_explicit_error(self) -> None:
        original_token = stub_config.DISCORD_BOT_TOKEN
        setattr(stub_config, "DISCORD_BOT_TOKEN", "")

        try:
            with self.assertRaisesRegex(RuntimeError, MISSING_DISCORD_TOKEN_MESSAGE):
                get_discord_token()
        finally:
            setattr(stub_config, "DISCORD_BOT_TOKEN", original_token)

    async def test_missing_cogs_directory_raises_file_not_found(self) -> None:
        bot = OsuBot(command_prefix="!", intents=None, cogs_dir=Path("missing-cogs"))

        try:
            with self.assertRaises(FileNotFoundError):
                bot._discover_cog_names()
        finally:
            await bot.close()

    async def test_setup_hook_propagates_api_setup_failure(self) -> None:
        api = StubOsuApi(setup_error=RuntimeError("setup failed"))
        bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api)

        try:
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                await bot.setup_hook()
        finally:
            await bot.close()

        self.assertTrue(api.setup_called)

    async def test_setup_hook_propagates_cog_load_failure(self) -> None:
        api = StubOsuApi()

        with TemporaryDirectory() as temp_dir:
            cogs_dir = Path(temp_dir)
            (cogs_dir / "broken_cog.py").touch()
            bot = OsuBot(
                command_prefix="!", intents=None, osu_api_factory=lambda: api, cogs_dir=cogs_dir
            )

            try:
                with patch.object(
                    bot, "load_extension", new=AsyncMock(side_effect=RuntimeError("load failed"))
                ):
                    with self.assertRaisesRegex(RuntimeError, "load failed"):
                        await bot.setup_hook()
            finally:
                await bot.close()

        self.assertTrue(api.setup_called)

    async def test_setup_hook_propagates_command_sync_failure(self) -> None:
        api = StubOsuApi()

        with TemporaryDirectory() as temp_dir:
            bot = OsuBot(
                command_prefix="!",
                intents=None,
                osu_api_factory=lambda: api,
                cogs_dir=Path(temp_dir),
            )

            try:
                with patch.object(
                    bot.tree, "sync", new=AsyncMock(side_effect=RuntimeError("sync failed"))
                ):
                    with self.assertRaisesRegex(RuntimeError, "sync failed"):
                        await bot.setup_hook()
            finally:
                await bot.close()

        self.assertTrue(api.setup_called)

    async def test_close_propagates_api_close_failure_after_bot_close(self) -> None:
        api = StubOsuApi(close_error=RuntimeError("close failed"))
        bot = OsuBot(command_prefix="!", intents=None, osu_api_factory=lambda: api)
        bot.osu_api_client = api

        with self.assertRaisesRegex(RuntimeError, "close failed"):
            await bot.close()

        self.assertTrue(api.close_called)
        self.assertTrue(bot.is_closed())


if __name__ == "__main__":
    unittest.main()
