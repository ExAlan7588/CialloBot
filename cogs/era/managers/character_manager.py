"""Era TW 角色管理器

管理角色狀態、屬性變化等。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from ..models.character import Character
from ..models.player import PlayerSave

if TYPE_CHECKING:
    from .game_manager import GameManager


class CharacterManager:
    """角色管理器

    處理角色狀態變化、好感度計算等。
    """

    def __init__(self, game_manager: "GameManager"):
        """初始化角色管理器

        Args:
            game_manager: 遊戲管理器引用
        """
        self.game_manager = game_manager

        # 設置雙向引用
        game_manager.set_character_manager(self)

    def get_character(self, char_id: int) -> Character | None:
        """取得角色基礎資料"""
        if not self.game_manager.csv_loader:
            return None
        return self.game_manager.csv_loader.get_character(char_id)

    def get_character_state(self, discord_id: int, char_id: int) -> dict[str, Any] | None:
        """取得角色狀態（玩家特定）"""
        save = self.game_manager.get_player_save(discord_id)
        if not save:
            return None
        return save.character_states.get(char_id)

    def update_character_state(
        self, discord_id: int, char_id: int, updates: dict[str, Any]
    ) -> bool:
        """更新角色狀態

        Args:
            discord_id: 玩家 ID
            char_id: 角色 ID
            updates: 要更新的屬性字典

        Returns:
            是否更新成功
        """
        save = self.game_manager.get_player_save(discord_id)
        if not save:
            return False

        if char_id not in save.character_states:
            save.character_states[char_id] = {}

        save.character_states[char_id].update(updates)
        return True

    # === 好感度系統 ===

    def get_affection(self, discord_id: int, char_id: int) -> int:
        """取得角色好感度"""
        state = self.get_character_state(discord_id, char_id)
        if not state:
            return 0
        return state.get("affection", 0)

    def add_affection(
        self, discord_id: int, char_id: int, amount: int, reason: str = ""
    ) -> tuple[int, str]:
        """增加好感度

        Args:
            discord_id: 玩家 ID
            char_id: 角色 ID
            amount: 增加量
            reason: 原因說明

        Returns:
            (新的好感度, 訊息)
        """
        state = self.get_character_state(discord_id, char_id)
        if not state:
            return 0, "找不到角色狀態"

        old_affection = state.get("affection", 0)
        new_affection = min(max(old_affection + amount, -1000), 1000)  # 限制在 -1000 ~ 1000

        self.update_character_state(discord_id, char_id, {"affection": new_affection})

        char = self.get_character(char_id)
        name = char.callname if char else f"角色{char_id}"

        if amount > 0:
            msg = f"💕 {name} 的好感度上升了 +{amount} ({old_affection} → {new_affection})"
        else:
            msg = f"💔 {name} 的好感度下降了 {amount} ({old_affection} → {new_affection})"

        if reason:
            msg += f" ({reason})"

        return new_affection, msg

    # === 關係階段 ===

    def get_relationship_level(self, discord_id: int, char_id: int) -> int:
        """取得關係等級

        0: 陌生人 (0-99)
        1: 認識 (100-299)
        2: 朋友 (300-499)
        3: 好友 (500-699)
        4: 親密 (700-899)
        5: 戀人 (900+)
        """
        affection = self.get_affection(discord_id, char_id)

        if affection >= 900:
            return 5
        elif affection >= 700:
            return 4
        elif affection >= 500:
            return 3
        elif affection >= 300:
            return 2
        elif affection >= 100:
            return 1
        else:
            return 0

    def get_relationship_name(self, discord_id: int, char_id: int) -> str:
        """取得關係名稱"""
        level = self.get_relationship_level(discord_id, char_id)
        names = {0: "陌生人", 1: "認識", 2: "朋友", 3: "好友", 4: "親密", 5: "戀人"}
        return names.get(level, "未知")

    # === 角色列表 ===

    def get_all_characters(self) -> list[Character]:
        """取得所有角色"""
        if not self.game_manager.csv_loader:
            return []
        return list(self.game_manager.csv_loader.characters.values())

    def get_characters_by_affection(
        self, discord_id: int, min_affection: int = 0
    ) -> list[tuple[Character, int]]:
        """取得按好感度排序的角色列表

        Args:
            discord_id: 玩家 ID
            min_affection: 最低好感度閾值

        Returns:
            (角色, 好感度) 列表，按好感度降序排列
        """
        characters = self.get_all_characters()
        result = []

        for char in characters:
            affection = self.get_affection(discord_id, char.id)
            if affection >= min_affection:
                result.append((char, affection))

        result.sort(key=lambda x: x[1], reverse=True)
        return result

    # === 角色狀態檢查 ===

    def is_lover(self, discord_id: int, char_id: int) -> bool:
        """檢查是否為戀人"""
        state = self.get_character_state(discord_id, char_id)
        if not state:
            return False
        return state.get("is_lover", False)

    def set_lover(self, discord_id: int, char_id: int, is_lover: bool = True) -> None:
        """設置戀人狀態"""
        self.update_character_state(discord_id, char_id, {"is_lover": is_lover})

    def get_times_met(self, discord_id: int, char_id: int) -> int:
        """取得見面次數"""
        state = self.get_character_state(discord_id, char_id)
        if not state:
            return 0
        return state.get("times_met", 0)

    def increment_times_met(self, discord_id: int, char_id: int) -> int:
        """增加見面次數"""
        times = self.get_times_met(discord_id, char_id) + 1
        self.update_character_state(discord_id, char_id, {"times_met": times})
        return times
