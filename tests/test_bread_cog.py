from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from discord import app_commands
from discord.ext import commands

from cogs.bread_cog import BreadCog


class BreadCogActorNicknameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cog = BreadCog(bot=cast(commands.Bot, SimpleNamespace()))

    async def test_action_commands_use_bread_actor_nickname_in_embed_author(self) -> None:
        test_cases = [
            {
                "command": BreadCog.bread_buy,
                "patch_target": "cogs.bread_cog.buy_items",
                "result": SimpleNamespace(
                    actor_nickname="BreadActor",
                    item_name="可頌",
                    delta=3,
                    message="buy ok",
                    event_name="normal_buy",
                    previous_item_count=1,
                    current_item_count=4,
                ),
                "callback_args": (),
                "expected_author": "BreadActor 的 可頌 採購結果",
                "expected_call_kwargs": {
                    "guild_id": 123,
                    "user_id": 456,
                    "fallback_nickname": "DiscordActor",
                },
            },
            {
                "command": BreadCog.bread_eat,
                "patch_target": "cogs.bread_cog.eat_items",
                "result": SimpleNamespace(
                    actor_nickname="BreadActor",
                    item_name="可頌",
                    message="eat ok",
                    event_name="normal_eat",
                    previous_item_count=5,
                    current_item_count=3,
                    previous_level=1,
                    current_level=2,
                ),
                "callback_args": (),
                "expected_author": "BreadActor 的 可頌 食用結果",
                "expected_call_kwargs": {
                    "guild_id": 123,
                    "user_id": 456,
                    "fallback_nickname": "DiscordActor",
                },
            },
            {
                "command": BreadCog.bread_give,
                "patch_target": "cogs.bread_cog.give_items",
                "result": SimpleNamespace(
                    actor_nickname="BreadActor",
                    item_name="可頌",
                    message="give ok",
                    event_name="normal_give",
                    previous_item_count=5,
                    current_item_count=3,
                    target_nickname="TargetBread",
                ),
                "callback_args": (None,),
                "expected_author": "BreadActor 的 可頌 贈送結果",
                "expected_call_kwargs": {
                    "guild_id": 123,
                    "actor_user_id": 456,
                    "actor_fallback_nickname": "DiscordActor",
                    "target_user_id": None,
                },
            },
            {
                "command": BreadCog.bread_rob,
                "patch_target": "cogs.bread_cog.rob_items",
                "result": SimpleNamespace(
                    actor_nickname="BreadActor",
                    item_name="可頌",
                    actor_delta=2,
                    message="rob ok",
                    event_name="normal_rob",
                    previous_item_count=5,
                    current_item_count=7,
                    target_nickname="TargetBread",
                ),
                "callback_args": (None,),
                "expected_author": "BreadActor 的 可頌 搶奪結果",
                "expected_call_kwargs": {
                    "guild_id": 123,
                    "actor_user_id": 456,
                    "actor_fallback_nickname": "DiscordActor",
                    "target_user_id": None,
                },
            },
            {
                "command": BreadCog.bread_bet,
                "patch_target": "cogs.bread_cog.bet_items",
                "result": SimpleNamespace(
                    actor_nickname="BreadActor",
                    item_name="可頌",
                    delta=2,
                    message="bet ok",
                    event_name="win",
                    previous_item_count=5,
                    current_item_count=7,
                    player_gesture="剪刀",
                    system_gesture="布",
                ),
                "callback_args": (app_commands.Choice(name="剪刀", value="剪刀"),),
                "expected_author": "BreadActor 的 可頌 賭局結果",
                "expected_call_kwargs": {
                    "guild_id": 123,
                    "user_id": 456,
                    "fallback_nickname": "DiscordActor",
                    "gesture": "剪刀",
                },
            },
        ]

        for case in test_cases:
            with self.subTest(command=case["expected_author"]):
                interaction = self._build_interaction()
                with patch(case["patch_target"], AsyncMock(return_value=case["result"])) as mocked_call:
                    await case["command"].callback(self.cog, interaction, *case["callback_args"])

                mocked_call.assert_awaited_once_with(**case["expected_call_kwargs"])
                send_message = interaction.response.send_message
                send_message.assert_awaited_once()
                embed = send_message.await_args.kwargs["embed"]
                self.assertEqual(embed.author.name, case["expected_author"])

    async def test_bread_profile_uses_fallback_nickname_argument(self) -> None:
        interaction = self._build_interaction()
        with patch(
            "cogs.bread_cog.get_profile_data",
            AsyncMock(
                return_value={
                    "item_name": "可頌",
                    "nickname": "BreadActor",
                    "item_count": 3,
                    "level": 1,
                    "xp": 2,
                    "remaining_to_level": 8,
                    "level_target": 10,
                }
            ),
        ) as mocked_get_profile_data:
            callback = cast(Any, BreadCog.bread_profile.callback)
            await callback(self.cog, interaction, None)

        mocked_get_profile_data.assert_awaited_once_with(
            guild_id=123,
            user_id=456,
            fallback_nickname="DiscordActor",
        )

    async def test_bread_nickname_uses_fallback_nickname_argument(self) -> None:
        interaction = self._build_interaction()
        with patch(
            "cogs.bread_cog.set_bread_nickname",
            AsyncMock(return_value=SimpleNamespace(old_nickname="Old", new_nickname="New")),
        ) as mocked_set_bread_nickname:
            callback = cast(Any, BreadCog.bread_nickname.callback)
            await callback(self.cog, interaction, "New")

        mocked_set_bread_nickname.assert_awaited_once_with(
            guild_id=123,
            user_id=456,
            fallback_nickname="DiscordActor",
            new_nickname="New",
        )

    async def test_bread_rank_defaults_to_group_scope(self) -> None:
        interaction = self._build_interaction()
        response_message = SimpleNamespace()
        interaction.original_response = AsyncMock(return_value=response_message)
        ranking_view = SimpleNamespace(message=None)
        with patch(
            "cogs.bread_cog.create_ranking_response",
            AsyncMock(return_value=("embed", ranking_view)),
        ) as mocked_create_ranking_response:
            callback = cast(Any, BreadCog.bread_rank.callback)
            await callback(self.cog, interaction, None)

        mocked_create_ranking_response.assert_awaited_once_with(
            bot=self.cog.bot,
            author=interaction.user,
            scope="group",
            guild_id=123,
        )
        interaction.response.send_message.assert_awaited_once_with(embed="embed", view=ranking_view)
        interaction.original_response.assert_awaited_once_with()
        self.assertIs(ranking_view.message, response_message)

    async def test_bread_rank_maps_non_group_choice_to_global_scope(self) -> None:
        interaction = self._build_interaction()
        response_message = SimpleNamespace()
        interaction.original_response = AsyncMock(return_value=response_message)
        ranking_view = SimpleNamespace(message=None)
        with patch(
            "cogs.bread_cog.create_ranking_response",
            AsyncMock(return_value=("embed", ranking_view)),
        ) as mocked_create_ranking_response:
            callback = cast(Any, BreadCog.bread_rank.callback)
            await callback(
                self.cog,
                interaction,
                app_commands.Choice(name="全局排行榜", value="global"),
            )

        mocked_create_ranking_response.assert_awaited_once_with(
            bot=self.cog.bot,
            author=interaction.user,
            scope="global",
            guild_id=123,
        )
        interaction.response.send_message.assert_awaited_once_with(embed="embed", view=ranking_view)
        interaction.original_response.assert_awaited_once_with()
        self.assertIs(ranking_view.message, response_message)

    @staticmethod
    def _build_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            guild_id=123,
            user=SimpleNamespace(id=456, display_name="DiscordActor", bot=False),
            response=SimpleNamespace(send_message=AsyncMock()),
            original_response=AsyncMock(),
        )


if __name__ == "__main__":
    unittest.main()
