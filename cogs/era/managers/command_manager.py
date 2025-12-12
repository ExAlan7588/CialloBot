"""Era TW 指令管理器

管理遊戲指令的執行和效果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Any
import random

from loguru import logger

from ..data.constants import COMMANDS, COMMAND_CATEGORIES, TIME_COSTS, STAMINA_COSTS
from ..models.enums import CommandCategory

if TYPE_CHECKING:
    from .game_manager import GameManager
    from .character_manager import CharacterManager


@dataclass
class CommandResult:
    """指令執行結果"""

    success: bool
    message: str
    affection_change: int = 0
    time_passed: int = 0
    effects: dict[str, Any] | None = None


class CommandManager:
    """指令管理器

    處理遊戲指令的註冊和執行。
    """

    def __init__(self, game_manager: "GameManager", character_manager: "CharacterManager"):
        """初始化指令管理器

        Args:
            game_manager: 遊戲管理器
            character_manager: 角色管理器
        """
        self.game_manager = game_manager
        self.character_manager = character_manager

        # 指令處理器註冊表
        self._handlers: dict[int, Callable[..., CommandResult]] = {}

        # 註冊預設指令
        self._register_default_commands()

    def _register_default_commands(self) -> None:
        """註冊預設指令處理器"""
        # 日常系
        self._handlers[300] = self._cmd_conversation  # 会话
        self._handlers[301] = self._cmd_tea  # 泡茶
        self._handlers[302] = self._cmd_touch  # 身体接触
        self._handlers[309] = self._cmd_headpat  # 摸头
        self._handlers[311] = self._cmd_hug  # 拥抱
        self._handlers[312] = self._cmd_kiss  # 接吻

        # 交流系
        self._handlers[20] = self._cmd_kiss  # 接吻
        self._handlers[22] = self._cmd_tempt  # 诱惑

        # 特殊
        self._handlers[352] = self._cmd_confess  # 告白

    def get_available_commands(
        self, discord_id: int, category: str | None = None
    ) -> list[tuple[int, str]]:
        """取得可用指令列表

        Args:
            discord_id: 玩家 ID
            category: 指令類別（可選）

        Returns:
            (指令ID, 指令名稱) 列表
        """
        save = self.game_manager.get_player_save(discord_id)
        if not save:
            return []

        target_id = save.progress.current_target_id
        if not target_id:
            return []

        relationship_level = self.character_manager.get_relationship_level(discord_id, target_id)

        available = []

        if category:
            cmd_ids = COMMAND_CATEGORIES.get(category, [])
        else:
            cmd_ids = list(COMMANDS.keys())

        for cmd_id in cmd_ids:
            # 檢查指令是否解鎖（基於關係等級）
            if self._is_command_available(cmd_id, relationship_level):
                name = COMMANDS.get(cmd_id, f"指令{cmd_id}")
                available.append((cmd_id, name))

        return available

    def _is_command_available(self, cmd_id: int, relationship_level: int) -> bool:
        """檢查指令是否可用"""
        # 基本指令：所有人可用
        basic_commands = [300, 301, 302, 309]
        if cmd_id in basic_commands:
            return True

        # 親密指令：需要朋友以上
        intimate_commands = [311, 312, 20]
        if cmd_id in intimate_commands:
            return relationship_level >= 2

        # 特殊指令：需要好友以上
        special_commands = [22, 352]
        if cmd_id in special_commands:
            return relationship_level >= 3

        # 預設可用
        return True

    async def execute_command(self, discord_id: int, cmd_id: int) -> CommandResult:
        """執行指令

        Args:
            discord_id: 玩家 ID
            cmd_id: 指令 ID

        Returns:
            CommandResult 執行結果
        """
        save = self.game_manager.get_player_save(discord_id)
        if not save:
            return CommandResult(False, "找不到存檔")

        target_id = save.progress.current_target_id
        if not target_id:
            return CommandResult(False, "沒有互動對象")

        # 取得角色資訊
        target = self.character_manager.get_character(target_id)
        if not target:
            return CommandResult(False, "找不到目標角色")

        # 查找指令處理器
        handler = self._handlers.get(cmd_id)
        if handler:
            result = handler(discord_id, target_id)
        else:
            # 通用處理
            result = self._cmd_generic(discord_id, target_id, cmd_id)

        # 更新統計
        self.game_manager.increment_command_count(discord_id)

        # 推進時間
        if result.time_passed > 0:
            self.game_manager.advance_time(discord_id, result.time_passed)

        # 應用好感度變化
        if result.affection_change != 0:
            self.character_manager.add_affection(discord_id, target_id, result.affection_change)

        return result

    # === 指令處理器 ===

    def _cmd_conversation(self, discord_id: int, target_id: int) -> CommandResult:
        """会话"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        # 隨機好感度變化
        affection = random.randint(1, 5)

        messages = [
            f"與 {name} 進行了愉快的對話。",
            f"{name} 似乎很享受和你聊天。",
            f"你們聊了很多有趣的話題。",
        ]

        return CommandResult(
            success=True,
            message=random.choice(messages),
            affection_change=affection,
            time_passed=TIME_COSTS["conversation"],
        )

    def _cmd_tea(self, discord_id: int, target_id: int) -> CommandResult:
        """泡茶"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        affection = random.randint(2, 6)

        return CommandResult(
            success=True,
            message=f"你為 {name} 泡了一杯茶。{name} 看起來很開心。",
            affection_change=affection,
            time_passed=10,
        )

    def _cmd_touch(self, discord_id: int, target_id: int) -> CommandResult:
        """身体接触"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        relationship = self.character_manager.get_relationship_level(discord_id, target_id)

        if relationship < 1:
            return CommandResult(
                success=False,
                message=f"{name} 躲開了你的接觸。",
                affection_change=-2,
                time_passed=5,
            )

        affection = random.randint(1, 4)
        return CommandResult(
            success=True,
            message=f"你輕輕碰觸了 {name}。",
            affection_change=affection,
            time_passed=5,
        )

    def _cmd_headpat(self, discord_id: int, target_id: int) -> CommandResult:
        """摸头"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        affection = random.randint(3, 8)

        messages = [
            f"你輕輕撫摸 {name} 的頭。{name} 害羞地低下頭。",
            f"{name} 乖乖地讓你摸頭，看起來很舒服。",
            f"「嗯...」{name} 閉上眼睛，享受著你的撫摸。",
        ]

        return CommandResult(
            success=True, message=random.choice(messages), affection_change=affection, time_passed=5
        )

    def _cmd_hug(self, discord_id: int, target_id: int) -> CommandResult:
        """拥抱"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        relationship = self.character_manager.get_relationship_level(discord_id, target_id)

        if relationship < 2:
            return CommandResult(
                success=False,
                message=f"{name} 推開了你。「太、太近了！」",
                affection_change=-3,
                time_passed=5,
            )

        affection = random.randint(5, 12)

        return CommandResult(
            success=True,
            message=f"你輕輕抱住了 {name}。{name} 的臉微微泛紅。",
            affection_change=affection,
            time_passed=10,
        )

    def _cmd_kiss(self, discord_id: int, target_id: int) -> CommandResult:
        """接吻"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        relationship = self.character_manager.get_relationship_level(discord_id, target_id)

        if relationship < 3:
            return CommandResult(
                success=False,
                message=f"{name} 驚訝地躲開了！「你在做什麼！」",
                affection_change=-10,
                time_passed=5,
            )

        affection = random.randint(10, 20)

        return CommandResult(
            success=True,
            message=f"你輕輕吻了 {name}。{name} 的臉變得通紅。",
            affection_change=affection,
            time_passed=15,
        )

    def _cmd_tempt(self, discord_id: int, target_id: int) -> CommandResult:
        """诱惑"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        success = random.random() > 0.4

        if success:
            affection = random.randint(5, 15)
            return CommandResult(
                success=True,
                message=f"你的誘惑對 {name} 產生了效果... {name} 臉紅了。",
                affection_change=affection,
                time_passed=10,
            )
        else:
            return CommandResult(
                success=False,
                message=f"{name} 不為所動。「你在做什麼奇怪的事？」",
                affection_change=-5,
                time_passed=10,
            )

    def _cmd_confess(self, discord_id: int, target_id: int) -> CommandResult:
        """告白"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"

        affection = self.character_manager.get_affection(discord_id, target_id)

        # 告白成功需要高好感度
        if affection >= 800:
            self.character_manager.set_lover(discord_id, target_id, True)
            return CommandResult(
                success=True,
                message=f"「我...我也喜歡你！」{name} 接受了你的告白！💕\n\n恭喜！你和 {name} 成為戀人了！",
                affection_change=100,
                time_passed=30,
                effects={"became_lover": True},
            )
        elif affection >= 500:
            return CommandResult(
                success=False,
                message=f"{name} 低下頭...「對不起，我還需要時間...」\n\n繼續增進感情吧！",
                affection_change=10,  # 告白本身也會增加好感
                time_passed=30,
            )
        else:
            return CommandResult(
                success=False,
                message=f"{name} 驚訝地看著你。「這...這也太突然了！」",
                affection_change=-20,
                time_passed=30,
            )

    def _cmd_generic(self, discord_id: int, target_id: int, cmd_id: int) -> CommandResult:
        """通用指令處理"""
        target = self.character_manager.get_character(target_id)
        name = target.callname if target else "對方"
        cmd_name = COMMANDS.get(cmd_id, f"指令{cmd_id}")

        # 隨機效果
        affection = random.randint(-2, 5)

        return CommandResult(
            success=True,
            message=f"對 {name} 執行了「{cmd_name}」。",
            affection_change=affection,
            time_passed=10,
        )
