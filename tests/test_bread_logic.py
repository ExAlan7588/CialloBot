from __future__ import annotations

import unittest
from unittest.mock import patch

from bread.services.bet_service import _resolve_base_bet_outcome
from bread.services.eat_service import _resolve_eat_event
from bread.services.record_service import _build_preview_text, _map_action_label


class BreadLogicTests(unittest.TestCase):
    def test_bet_outcome_win(self) -> None:
        delta, event_name = _resolve_base_bet_outcome(
            gesture="剪刀",
            system_gesture="布",
            bet_amount=6,
        )
        self.assertEqual(delta, 6)
        self.assertEqual(event_name, "win")

    def test_bet_outcome_lose(self) -> None:
        delta, event_name = _resolve_base_bet_outcome(
            gesture="布",
            system_gesture="剪刀",
            bet_amount=6,
        )
        self.assertEqual(delta, -6)
        self.assertEqual(event_name, "lose")

    def test_bet_outcome_draw(self) -> None:
        delta, event_name = _resolve_base_bet_outcome(
            gesture="石頭",
            system_gesture="石頭",
            bet_amount=6,
        )
        self.assertEqual(delta, 0)
        self.assertEqual(event_name, "draw")

    @patch("bread.services.eat_service.random", return_value=0.205)
    def test_eat_event_normal(self, _mock_random) -> None:
        event = _resolve_eat_event(previous_item_count=20, eat_amount=5)
        self.assertEqual(event["event_name"], "normal_eat")
        self.assertEqual(event["consumed_amount"], 5)

    @patch("bread.services.eat_service.random", return_value=0.095)
    def test_eat_event_too_full(self, _mock_random) -> None:
        event = _resolve_eat_event(previous_item_count=20, eat_amount=5)
        self.assertEqual(event["event_name"], "too_full")
        self.assertGreater(int(event["cooldown_seconds"]), 4800)

    def test_record_action_label_includes_rename(self) -> None:
        self.assertEqual(_map_action_label("rename"), "改名")

    def test_record_preview_only_keeps_first_line(self) -> None:
        preview = _build_preview_text("第一行摘要\n第二行不應該出現")
        self.assertEqual(preview, "第一行摘要")


if __name__ == "__main__":
    unittest.main()
