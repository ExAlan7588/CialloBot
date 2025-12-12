"""Era TW 玩家存檔模型

定義玩家存檔數據結構，用於保存遊戲進度。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import GameState, Location, Weather, TimeOfDay


@dataclass
class GameProgress:
    """遊戲進度資料"""

    # 時間系統
    day: int = 1  # 遊戲天數
    time: int = 360  # 遊戲時間 (分鐘，360 = 6:00 AM)

    # 天氣
    weather: Weather = Weather.SUNNY

    # 位置
    current_location: Location = Location.HAKUREI_SHRINE

    # 金錢
    money: int = 1000

    # 當前狀態
    game_state: GameState = GameState.IDLE
    current_target_id: int | None = None  # 當前互動的角色 ID

    @property
    def time_of_day(self) -> TimeOfDay:
        """取得當前時段"""
        hour = self.time // 60
        if 4 <= hour < 6:
            return TimeOfDay.DAWN
        elif 6 <= hour < 12:
            return TimeOfDay.MORNING
        elif 12 <= hour < 18:
            return TimeOfDay.AFTERNOON
        elif 18 <= hour < 20:
            return TimeOfDay.EVENING
        else:
            return TimeOfDay.NIGHT

    @property
    def formatted_time(self) -> str:
        """格式化時間顯示"""
        hours = self.time // 60
        minutes = self.time % 60
        return f"{hours:02d}:{minutes:02d}"

    def advance_time(self, minutes: int) -> bool:
        """推進時間，返回是否進入新的一天"""
        self.time += minutes
        if self.time >= 1440:  # 24 * 60
            self.time %= 1440
            self.day += 1
            return True
        return False


@dataclass
class Inventory:
    """物品欄"""

    items: dict[str, int] = field(default_factory=dict)  # item_id -> quantity

    def add_item(self, item_id: str, quantity: int = 1) -> None:
        """添加物品"""
        self.items[item_id] = self.items.get(item_id, 0) + quantity

    def remove_item(self, item_id: str, quantity: int = 1) -> bool:
        """移除物品，返回是否成功"""
        current = self.items.get(item_id, 0)
        if current < quantity:
            return False
        self.items[item_id] = current - quantity
        if self.items[item_id] <= 0:
            del self.items[item_id]
        return True

    def has_item(self, item_id: str, quantity: int = 1) -> bool:
        """檢查是否擁有足夠數量的物品"""
        return self.items.get(item_id, 0) >= quantity


@dataclass
class PlayerSave:
    """玩家完整存檔

    包含玩家的所有遊戲數據
    """

    # Discord 用戶資訊
    discord_id: int
    discord_name: str = ""

    # 遊戲進度
    progress: GameProgress = field(default_factory=GameProgress)

    # 物品欄
    inventory: Inventory = field(default_factory=Inventory)

    # 角色狀態 (character_id -> character data dict)
    character_states: dict[int, dict[str, Any]] = field(default_factory=dict)

    # 遊戲旗標
    flags: dict[str, int] = field(default_factory=dict)

    # 統計數據
    total_play_time: int = 0  # 總遊玩時間（分鐘）
    commands_executed: int = 0  # 執行的指令數

    # 時間戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 存檔槽位
    slot: int = 0

    def to_dict(self) -> dict[str, Any]:
        """轉換為可序列化的字典"""
        return {
            "discord_id": self.discord_id,
            "discord_name": self.discord_name,
            "progress": {
                "day": self.progress.day,
                "time": self.progress.time,
                "weather": self.progress.weather.value,
                "current_location": self.progress.current_location.value,
                "money": self.progress.money,
                "game_state": self.progress.game_state.value,
                "current_target_id": self.progress.current_target_id,
            },
            "inventory": self.inventory.items,
            "character_states": self.character_states,
            "flags": self.flags,
            "total_play_time": self.total_play_time,
            "commands_executed": self.commands_executed,
            "created_at": self.created_at.isoformat(),
            "updated_at": datetime.now().isoformat(),
            "slot": self.slot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerSave":
        """從字典創建存檔實例"""
        progress_data = data.get("progress", {})
        progress = GameProgress(
            day=progress_data.get("day", 1),
            time=progress_data.get("time", 360),
            weather=Weather(progress_data.get("weather", 0)),
            current_location=Location(progress_data.get("current_location", 0)),
            money=progress_data.get("money", 1000),
            game_state=GameState(progress_data.get("game_state", 0)),
            current_target_id=progress_data.get("current_target_id"),
        )

        inventory = Inventory(items=data.get("inventory", {}))

        return cls(
            discord_id=data["discord_id"],
            discord_name=data.get("discord_name", ""),
            progress=progress,
            inventory=inventory,
            character_states=data.get("character_states", {}),
            flags=data.get("flags", {}),
            total_play_time=data.get("total_play_time", 0),
            commands_executed=data.get("commands_executed", 0),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            slot=data.get("slot", 0),
        )


# 最大存檔槽位數
MAX_SAVE_SLOTS = 5
