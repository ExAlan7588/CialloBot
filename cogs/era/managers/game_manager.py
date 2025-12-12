"""Era TW 遊戲管理器

核心遊戲邏輯管理器，處理遊戲狀態和流程控制。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..data.csv_loader import CSVLoader
from ..data.constants import DEFAULT_SETTINGS, TIME_COSTS, STAMINA_COSTS
from ..models.character import Character
from ..models.enums import GameState, Location, Weather, TimeOfDay
from ..models.player import PlayerSave, GameProgress

if TYPE_CHECKING:
    from ..managers.character_manager import CharacterManager


class GameManager:
    """遊戲管理器

    管理遊戲狀態、時間流逝、事件觸發等核心邏輯。
    """

    def __init__(self, era_path: str | Path | None = None):
        """初始化遊戲管理器

        Args:
            era_path: eraTW 資料路徑
        """
        self.era_path = Path(era_path) if era_path else None
        self.csv_loader: CSVLoader | None = None

        # 玩家存檔快取 (discord_id -> PlayerSave)
        self._player_saves: dict[int, PlayerSave] = {}

        # 角色管理器引用
        self._character_manager: CharacterManager | None = None

        # 是否已初始化
        self._initialized = False

    async def initialize(self, era_path: str | Path | None = None) -> bool:
        """異步初始化

        Args:
            era_path: eraTW 資料路徑

        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True

        try:
            if era_path:
                self.era_path = Path(era_path)

            if self.era_path and self.era_path.exists():
                self.csv_loader = CSVLoader(self.era_path)
                # 在線程池中執行 CSV 載入（避免阻塞事件循環）
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.csv_loader.load_all, True)
                logger.info(f"遊戲資料載入完成: {len(self.csv_loader.characters)} 個角色")
            else:
                logger.warning("未指定 eraTW 路徑或路徑不存在，使用預設資料")

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"遊戲管理器初始化失敗: {e}")
            return False

    def set_character_manager(self, manager: "CharacterManager") -> None:
        """設置角色管理器引用"""
        self._character_manager = manager

    # === 玩家存檔管理 ===

    def get_player_save(self, discord_id: int) -> PlayerSave | None:
        """取得玩家存檔"""
        return self._player_saves.get(discord_id)

    def create_new_game(self, discord_id: int, discord_name: str = "") -> PlayerSave:
        """創建新遊戲

        Args:
            discord_id: Discord 用戶 ID
            discord_name: Discord 用戶名稱

        Returns:
            新的 PlayerSave
        """
        progress = GameProgress(
            day=DEFAULT_SETTINGS["start_day"],
            time=DEFAULT_SETTINGS["start_time"],
            money=DEFAULT_SETTINGS["start_money"],
            current_location=Location(DEFAULT_SETTINGS["start_location"]),
            game_state=GameState.EXPLORING,
        )

        save = PlayerSave(discord_id=discord_id, discord_name=discord_name, progress=progress)

        # 初始化角色狀態
        if self.csv_loader:
            for char_id, char in self.csv_loader.characters.items():
                save.character_states[char_id] = self._create_initial_character_state(char)

        self._player_saves[discord_id] = save
        logger.info(f"創建新遊戲: {discord_name} ({discord_id})")

        return save

    def _create_initial_character_state(self, character: Character) -> dict[str, Any]:
        """創建角色初始狀態"""
        return {"affection": 0, "trust": 0, "times_met": 0, "relationship_level": 0, "flags": {}}

    def has_save(self, discord_id: int) -> bool:
        """檢查玩家是否有存檔"""
        return discord_id in self._player_saves

    def delete_save(self, discord_id: int) -> bool:
        """刪除玩家存檔"""
        if discord_id in self._player_saves:
            del self._player_saves[discord_id]
            return True
        return False

    # === 時間系統 ===

    def advance_time(self, discord_id: int, minutes: int) -> tuple[bool, str]:
        """推進遊戲時間

        Args:
            discord_id: 玩家 ID
            minutes: 推進的分鐘數

        Returns:
            (是否進入新的一天, 時間變更描述)
        """
        save = self.get_player_save(discord_id)
        if not save:
            return False, "找不到存檔"

        old_time = save.progress.formatted_time
        old_day = save.progress.day
        new_day = save.progress.advance_time(minutes)

        message = f"時間推進: {old_time} → {save.progress.formatted_time}"
        if new_day:
            message += f" (第{old_day}天 → 第{save.progress.day}天)"

        return new_day, message

    def get_current_time_period(self, discord_id: int) -> TimeOfDay:
        """取得當前時段"""
        save = self.get_player_save(discord_id)
        if not save:
            return TimeOfDay.MORNING
        return save.progress.time_of_day

    # === 位置系統 ===

    def move_to_location(self, discord_id: int, location: Location) -> tuple[bool, str]:
        """移動到指定位置

        Args:
            discord_id: 玩家 ID
            location: 目標位置

        Returns:
            (是否成功, 訊息)
        """
        save = self.get_player_save(discord_id)
        if not save:
            return False, "找不到存檔"

        if save.progress.current_location == location:
            return False, "你已經在這裡了"

        # 消耗時間和體力
        self.advance_time(discord_id, TIME_COSTS["travel"])

        old_loc = save.progress.current_location.name
        save.progress.current_location = location

        return True, f"從 {old_loc} 移動到 {location.name}"

    # === 角色互動 ===

    def get_available_characters(self, discord_id: int) -> list[Character]:
        """取得當前可互動的角色"""
        save = self.get_player_save(discord_id)
        if not save or not self.csv_loader:
            return []

        current_time = save.progress.time
        available = []

        for char_id, char in self.csv_loader.characters.items():
            if char.is_available(current_time):
                available.append(char)

        return available

    def set_interaction_target(self, discord_id: int, target_id: int) -> tuple[bool, str]:
        """設置互動目標角色

        Args:
            discord_id: 玩家 ID
            target_id: 目標角色 ID

        Returns:
            (是否成功, 訊息)
        """
        save = self.get_player_save(discord_id)
        if not save:
            return False, "找不到存檔"

        if not self.csv_loader:
            return False, "遊戲資料未載入"

        char = self.csv_loader.get_character(target_id)
        if not char:
            return False, "找不到該角色"

        save.progress.current_target_id = target_id
        save.progress.game_state = GameState.INTERACTING

        return True, f"開始與 {char.callname} 互動"

    def end_interaction(self, discord_id: int) -> tuple[bool, str]:
        """結束當前互動"""
        save = self.get_player_save(discord_id)
        if not save:
            return False, "找不到存檔"

        save.progress.current_target_id = None
        save.progress.game_state = GameState.EXPLORING

        return True, "結束互動"

    def get_current_target(self, discord_id: int) -> Character | None:
        """取得當前互動的角色"""
        save = self.get_player_save(discord_id)
        if not save or not save.progress.current_target_id:
            return None

        if not self.csv_loader:
            return None

        return self.csv_loader.get_character(save.progress.current_target_id)

    # === 金錢系統 ===

    def add_money(self, discord_id: int, amount: int) -> tuple[bool, int]:
        """增加金錢"""
        save = self.get_player_save(discord_id)
        if not save:
            return False, 0

        save.progress.money += amount
        return True, save.progress.money

    def spend_money(self, discord_id: int, amount: int) -> tuple[bool, str]:
        """花費金錢"""
        save = self.get_player_save(discord_id)
        if not save:
            return False, "找不到存檔"

        if save.progress.money < amount:
            return False, f"金錢不足 (擁有: {save.progress.money}, 需要: {amount})"

        save.progress.money -= amount
        return True, f"花費 {amount} 金錢，剩餘 {save.progress.money}"

    # === 統計更新 ===

    def increment_command_count(self, discord_id: int) -> None:
        """增加指令執行計數"""
        save = self.get_player_save(discord_id)
        if save:
            save.commands_executed += 1

    def add_play_time(self, discord_id: int, minutes: int) -> None:
        """增加遊玩時間"""
        save = self.get_player_save(discord_id)
        if save:
            save.total_play_time += minutes
