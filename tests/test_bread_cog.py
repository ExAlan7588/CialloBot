from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
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
            },
        ]

        for case in test_cases:
            with self.subTest(command=case["expected_author"]):
                interaction = self._build_interaction()
                with patch(case["patch_target"], AsyncMock(return_value=case["result"])):
                    await case["command"].callback(self.cog, interaction, *case["callback_args"])

                send_message = interaction.response.send_message
                send_message.assert_awaited_once()
                embed = send_message.await_args.kwargs["embed"]
                self.assertEqual(embed.author.name, case["expected_author"])

    @staticmethod
    def _build_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            guild_id=123,
            user=SimpleNamespace(id=456, display_name="DiscordActor", bot=False),
            response=SimpleNamespace(send_message=AsyncMock()),
        )


if __name__ == "__main__":
    unittest.main()
