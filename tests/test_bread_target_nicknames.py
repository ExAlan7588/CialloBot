from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from bread.services.give_service import give_items
from bread.services.rob_service import rob_items


class BreadTargetNicknameTests(unittest.IsolatedAsyncioTestCase):
    async def test_give_uses_stored_bread_nickname_for_explicit_target(self) -> None:
        now = datetime.now(timezone.utc)
        actor_row = {
            "nickname": "ActorBread",
            "level": 2,
            "xp": 3,
            "item_count": 20,
            "buy_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "eat_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "rob_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "give_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "bet_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "updated_at": now,
        }
        target_row = {
            "nickname": "TargetBread",
            "level": 1,
            "xp": 0,
            "item_count": 4,
            "buy_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "eat_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "rob_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "give_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "bet_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "updated_at": now,
            "user_id": 99,
        }

        with (
            patch(
                "bread.services.give_service.get_transfer_context",
                AsyncMock(
                    return_value={
                        "config_row": {
                            "item_name": "面包",
                            "allow_random_give": True,
                        },
                        "actor_row": actor_row,
                        "target_row": target_row,
                        "was_random_target": False,
                    }
                ),
            ),
            patch("bread.services.give_service.randint", return_value=3),
            patch("bread.services.give_service.random", return_value=0.5),
            patch(
                "bread.services.give_service.execute_transfer_action",
                AsyncMock(
                    return_value={
                        "actor_updated_row": {
                            "nickname": "ActorBread",
                            "item_count": 17,
                            "give_cooldown_until": now,
                        },
                        "state_changed": False,
                    }
                ),
            ),
        ):
            result = await give_items(
                guild_id=123,
                actor_user_id=1,
                actor_nickname="DiscordActor",
                target_user_id=99,
            )

        self.assertEqual(result.actor_nickname, "ActorBread")
        self.assertEqual(result.target_nickname, "TargetBread")
        self.assertIn("[TargetBread]", result.message)

    async def test_rob_uses_stored_bread_nickname_for_explicit_target(self) -> None:
        now = datetime.now(timezone.utc)
        actor_row = {
            "nickname": "ActorBread",
            "level": 2,
            "xp": 3,
            "item_count": 20,
            "buy_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "eat_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "rob_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "give_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "bet_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "updated_at": now,
        }
        target_row = {
            "nickname": "TargetBread",
            "level": 1,
            "xp": 0,
            "item_count": 20,
            "buy_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "eat_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "rob_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "give_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "bet_cooldown_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "updated_at": now,
            "user_id": 77,
        }

        with (
            patch(
                "bread.services.rob_service.get_transfer_context",
                AsyncMock(
                    return_value={
                        "config_row": {
                            "item_name": "面包",
                            "allow_random_rob": True,
                        },
                        "actor_row": actor_row,
                        "target_row": target_row,
                        "was_random_target": False,
                    }
                ),
            ),
            patch("bread.services.rob_service.randint", return_value=4),
            patch("bread.services.rob_service.random", return_value=0.5),
            patch(
                "bread.services.rob_service.execute_transfer_action",
                AsyncMock(
                    return_value={
                        "actor_updated_row": {
                            "nickname": "ActorBread",
                            "item_count": 24,
                            "rob_cooldown_until": now,
                        },
                        "state_changed": False,
                    }
                ),
            ),
        ):
            result = await rob_items(
                guild_id=123,
                actor_user_id=1,
                actor_nickname="DiscordActor",
                target_user_id=77,
            )

        self.assertEqual(result.actor_nickname, "ActorBread")
        self.assertEqual(result.target_nickname, "TargetBread")
        self.assertIn("[TargetBread]", result.message)


if __name__ == "__main__":
    unittest.main()
