"""Era TW v2 - 使用 Discord Components V2 重構

核心改變：
1. 使用 ui.LayoutView 替代傳統 View
2. 地圖探索系統 - 移動到不同地點遇見角色
3. 簡化互動 - 直接顯示可用指令按鈕
4. PostgreSQL 持久化存檔
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from enum import Enum
import random

import discord
from discord import ui
from discord.ext import commands
from loguru import logger

if TYPE_CHECKING:
    from bot import OsuBot


# ============================================================
# 地圖系統
# ============================================================


class LocationType(Enum):
    """地點類型"""

    HAKUREI_SHRINE = ("博麗神社", "⛩️", "寧靜的神社，靈夢的家")
    SCARLET_MANOR = ("紅魔館", "🏰", "吸血鬼的華麗宅邸")
    HUMAN_VILLAGE = ("人間之里", "🏘️", "人類聚居的村落")
    MAGIC_FOREST = ("魔法森林", "🌲", "充滿神秘的森林")
    MORIYA_SHRINE = ("守矢神社", "🏔️", "山頂的神社")
    EIENTEI = ("永遠亭", "🏥", "隱藏在竹林中的宅邸")
    UNDERGROUND = ("地底", "🕳️", "舊地獄的遺址")
    NETHERWORLD = ("冥界", "👻", "亡靈的世界")

    @property
    def name_tw(self) -> str:
        return self.value[0]

    @property
    def emoji(self) -> str:
        return self.value[1]

    @property
    def description(self) -> str:
        return self.value[2]

    def as_option(self) -> discord.SelectOption:
        return discord.SelectOption(
            label=self.name_tw, value=self.name, emoji=self.emoji, description=self.description
        )


# 地點之間的連接關係
LOCATION_CONNECTIONS = {
    LocationType.HAKUREI_SHRINE: [LocationType.HUMAN_VILLAGE, LocationType.MAGIC_FOREST],
    LocationType.HUMAN_VILLAGE: [
        LocationType.HAKUREI_SHRINE,
        LocationType.SCARLET_MANOR,
        LocationType.MAGIC_FOREST,
    ],
    LocationType.SCARLET_MANOR: [LocationType.HUMAN_VILLAGE],
    LocationType.MAGIC_FOREST: [
        LocationType.HAKUREI_SHRINE,
        LocationType.HUMAN_VILLAGE,
        LocationType.MORIYA_SHRINE,
    ],
    LocationType.MORIYA_SHRINE: [LocationType.MAGIC_FOREST],
    LocationType.EIENTEI: [LocationType.HUMAN_VILLAGE],
    LocationType.UNDERGROUND: [LocationType.MORIYA_SHRINE],
    LocationType.NETHERWORLD: [LocationType.HAKUREI_SHRINE],
}

# 角色出沒地點
CHARACTER_LOCATIONS = {
    1: [LocationType.HAKUREI_SHRINE],  # 靈夢
    11: [LocationType.MAGIC_FOREST, LocationType.HAKUREI_SHRINE],  # 魔理沙
    15: [LocationType.SCARLET_MANOR],  # 咲夜
    16: [LocationType.SCARLET_MANOR],  # 蕾米莉亞
    50: [LocationType.SCARLET_MANOR],  # 芙蘭
    26: [LocationType.HAKUREI_SHRINE, LocationType.NETHERWORLD],  # 紫
    23: [LocationType.NETHERWORLD],  # 妖夢
    31: [LocationType.MORIYA_SHRINE],  # 早苗
    38: [LocationType.UNDERGROUND],  # 戀
    54: [LocationType.SCARLET_MANOR],  # 帕秋莉
}


# ============================================================
# 角色資料
# ============================================================


@dataclass
class Character:
    """角色資料"""

    id: int
    name: str  # 完整名稱
    callname: str  # 暱稱
    emoji: str
    description: str
    locations: list[LocationType] = field(default_factory=list)


CHARACTERS = {
    1: Character(
        1, "博麗 靈夢", "靈夢", "🎀", "樂園的巫女，博麗神社的巫女", [LocationType.HAKUREI_SHRINE]
    ),
    11: Character(
        11,
        "霧雨 魔理沙",
        "魔理沙",
        "⭐",
        "普通的魔法使",
        [LocationType.MAGIC_FOREST, LocationType.HAKUREI_SHRINE],
    ),
    15: Character(
        15, "十六夜 咲夜", "咲夜", "🔪", "紅魔館的完美女僕", [LocationType.SCARLET_MANOR]
    ),
    16: Character(
        16, "蕾米莉亞·斯卡蕾特", "蕾米", "🦇", "永遠的紅色幼月", [LocationType.SCARLET_MANOR]
    ),
    50: Character(50, "芙蘭朵露·斯卡蕾特", "芙蘭", "💎", "惡魔之妹", [LocationType.SCARLET_MANOR]),
    26: Character(
        26,
        "八雲 紫",
        "紫",
        "💜",
        "境界的妖怪",
        [LocationType.HAKUREI_SHRINE, LocationType.NETHERWORLD],
    ),
    23: Character(23, "魂魄 妖夢", "妖夢", "⚔️", "半人半靈的庭師", [LocationType.NETHERWORLD]),
    31: Character(31, "東風谷 早苗", "早苗", "🐍", "守矢神社的風祝", [LocationType.MORIYA_SHRINE]),
    38: Character(38, "古明地 戀", "戀", "💚", "關閉的戀之瞳", [LocationType.UNDERGROUND]),
    54: Character(
        54, "帕秋莉·諾蕾姬", "帕秋莉", "📚", "不動的大圖書館", [LocationType.SCARLET_MANOR]
    ),
}


# ============================================================
# 玩家資料
# ============================================================


@dataclass
class PlayerData:
    """玩家遊戲資料"""

    discord_id: int
    current_location: LocationType = LocationType.HAKUREI_SHRINE
    day: int = 1
    time: int = 360  # 06:00
    money: int = 1000
    affections: dict[int, int] = field(default_factory=dict)  # char_id -> affection

    def get_affection(self, char_id: int) -> int:
        return self.affections.get(char_id, 0)

    def add_affection(self, char_id: int, amount: int) -> int:
        current = self.affections.get(char_id, 0)
        new_val = max(-100, min(1000, current + amount))
        self.affections[char_id] = new_val
        return new_val

    @property
    def formatted_time(self) -> str:
        h = self.time // 60
        m = self.time % 60
        return f"{h:02d}:{m:02d}"

    @property
    def time_period(self) -> str:
        h = self.time // 60
        if 6 <= h < 12:
            return "☀️ 早晨"
        elif 12 <= h < 18:
            return "🌤️ 下午"
        elif 18 <= h < 21:
            return "🌆 傍晚"
        else:
            return "🌙 夜晚"


# 記憶體存儲（之後改為 PostgreSQL）
_player_data: dict[int, PlayerData] = {}


def get_player(discord_id: int) -> PlayerData:
    if discord_id not in _player_data:
        _player_data[discord_id] = PlayerData(discord_id=discord_id)
    return _player_data[discord_id]


# ============================================================
# Components V2 介面
# ============================================================


class LocationSelectRow(ui.ActionRow["ExploreView"]):
    """地點選擇列"""

    def __init__(self, player: PlayerData):
        super().__init__()
        self.player = player
        self._update_options()

    def _update_options(self):
        # 取得可前往的地點
        connections = LOCATION_CONNECTIONS.get(self.player.current_location, [])
        options = [loc.as_option() for loc in connections]

        if options:
            self.location_select.options = options
        else:
            # 沒有連接的地點，加入預設
            self.location_select.options = [discord.SelectOption(label="無處可去", value="none")]

    @ui.select(placeholder="🚶 選擇目的地...")
    async def location_select(self, interaction: discord.Interaction, select: ui.Select):
        if select.values[0] == "none":
            await interaction.response.send_message("這裡沒有其他地方可去！", ephemeral=True)
            return

        new_location = LocationType[select.values[0]]
        self.player.current_location = new_location
        self.player.time += 30  # 移動消耗 30 分鐘

        # 重新渲染整個視圖
        view = ExploreView(self.player)
        await interaction.response.edit_message(view=view)


class InteractionRow(ui.ActionRow["ExploreView"]):
    """互動按鈕列"""

    def __init__(self, player: PlayerData, character: Character | None):
        super().__init__()
        self.player = player
        self.character = character

    @ui.button(label="💬 交談", style=discord.ButtonStyle.primary)
    async def talk_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.character:
            await interaction.response.send_message("這裡沒有人可以交談", ephemeral=True)
            return

        affection = random.randint(2, 8)
        new_aff = self.player.add_affection(self.character.id, affection)
        self.player.time += 10

        messages = [
            f"與 {self.character.callname} 聊了一會兒。",
            f"{self.character.callname} 看起來很開心。",
            f"你們聊得很投機！",
        ]

        # 更新視圖
        view = ExploreView(self.player)
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"💕 {random.choice(messages)} (好感度 +{affection} → {new_aff})", ephemeral=True
        )

    @ui.button(label="🤝 摸頭", style=discord.ButtonStyle.secondary)
    async def headpat_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.character:
            await interaction.response.send_message("這裡沒有人！", ephemeral=True)
            return

        current_aff = self.player.get_affection(self.character.id)

        if current_aff < 100:
            self.player.add_affection(self.character.id, -5)
            msg = f"❌ {self.character.callname} 躲開了你的手！「我們還沒那麼熟吧...」"
        else:
            affection = random.randint(5, 15)
            new_aff = self.player.add_affection(self.character.id, affection)
            msg = f"💕 {self.character.callname} 乖乖讓你摸了頭！(好感度 +{affection} → {new_aff})"

        self.player.time += 5
        view = ExploreView(self.player)
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(msg, ephemeral=True)

    @ui.button(label="🎁 送禮", style=discord.ButtonStyle.secondary)
    async def gift_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.character:
            await interaction.response.send_message("這裡沒有人！", ephemeral=True)
            return

        if self.player.money < 100:
            await interaction.response.send_message("💰 金錢不足！", ephemeral=True)
            return

        self.player.money -= 100
        affection = random.randint(10, 25)
        new_aff = self.player.add_affection(self.character.id, affection)
        self.player.time += 5

        view = ExploreView(self.player)
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"🎁 送給 {self.character.callname} 一份禮物！(好感度 +{affection} → {new_aff})",
            ephemeral=True,
        )


class ExploreView(ui.LayoutView):
    """探索介面 - 使用 Components V2"""

    def __init__(self, player: PlayerData):
        super().__init__()
        self.player = player

        # 找出當前地點的角色
        location = player.current_location
        chars_here = [
            CHARACTERS[cid]
            for cid, locs in CHARACTER_LOCATIONS.items()
            if location in locs and cid in CHARACTERS
        ]
        current_char = random.choice(chars_here) if chars_here else None

        # === 主容器 ===
        container = ui.Container(accent_color=discord.Color.from_rgb(255, 107, 157))

        # 標題
        container.add_item(
            ui.TextDisplay(f"# {location.emoji} {location.name_tw}\n-# {location.description}")
        )

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # 狀態區塊
        status_text = (
            f"📅 **第 {player.day} 天** {player.formatted_time} ({player.time_period})\n"
            f"💰 **金錢:** {player.money:,}"
        )
        container.add_item(ui.TextDisplay(status_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # 角色區塊
        if current_char:
            affection = player.get_affection(current_char.id)
            rel_name = self._get_relationship_name(affection)

            char_text = (
                f"### {current_char.emoji} 遇見了 {current_char.callname}！\n"
                f"-# {current_char.description}\n"
                f"❤️ 好感度: **{affection}** ({rel_name})"
            )
            container.add_item(ui.TextDisplay(char_text))

            # 互動按鈕
            container.add_item(InteractionRow(player, current_char))
        else:
            container.add_item(
                ui.TextDisplay("### 這裡沒有發現任何人...\n-# 試著移動到其他地點吧！")
            )

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        # 移動選單
        container.add_item(ui.TextDisplay("### 🗺️ 前往其他地點"))
        container.add_item(LocationSelectRow(player))

        self.add_item(container)

    def _get_relationship_name(self, affection: int) -> str:
        if affection >= 900:
            return "💕 戀人"
        elif affection >= 700:
            return "💗 親密"
        elif affection >= 500:
            return "💖 好友"
        elif affection >= 300:
            return "❤️ 朋友"
        elif affection >= 100:
            return "🧡 認識"
        else:
            return "💔 陌生"


# ============================================================
# Cog
# ============================================================


class EraGameCog(commands.Cog, name="EraGame"):
    """eraTW 幻想鄉探索遊戲"""

    def __init__(self, bot: "OsuBot"):
        self.bot = bot

    @discord.app_commands.command(name="era", description="🌸 開始探索幻想鄉！")
    async def era_command(self, interaction: discord.Interaction):
        """開始/繼續遊戲"""
        player = get_player(interaction.user.id)
        view = ExploreView(player)
        await interaction.response.send_message(view=view)


async def setup(bot: "OsuBot"):
    await bot.add_cog(EraGameCog(bot))
