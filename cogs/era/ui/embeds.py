"""Era TW Discord UI Embeds

定義遊戲使用的 Discord Embed 模板。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ..data.constants import COLORS, MVP_CHARACTERS, COMMAND_CATEGORIES
from ..models.character import Character
from ..models.player import PlayerSave

if TYPE_CHECKING:
    from ..managers.character_manager import CharacterManager


class EraEmbeds:
    """Era 遊戲 Embed 工廠類"""

    @staticmethod
    def main_menu(player: PlayerSave) -> discord.Embed:
        """主選單 Embed"""
        embed = discord.Embed(
            title="🎮 eraTW - The World",
            description="歡迎來到幻想鄉！請選擇一個選項開始遊戲。",
            color=COLORS["primary"],
        )

        embed.add_field(
            name="📊 遊戲進度",
            value=f"第 {player.progress.day} 天 | {player.progress.formatted_time}",
            inline=True,
        )
        embed.add_field(name="💰 金錢", value=f"{player.progress.money:,}", inline=True)
        embed.add_field(
            name="📍 位置",
            value=player.progress.current_location.name.replace("_", " ").title(),
            inline=True,
        )

        embed.set_footer(text="使用下方按鈕進行操作")
        return embed

    @staticmethod
    def character_status(
        character: Character, affection: int, relationship_name: str
    ) -> discord.Embed:
        """角色狀態 Embed"""
        # 取得 MVP 角色 emoji
        char_info = MVP_CHARACTERS.get(character.id, {"emoji": "👤"})
        emoji = char_info.get("emoji", "👤")

        embed = discord.Embed(
            title=f"{emoji} {character.callname} 的狀態",
            description=character.description or f"「{character.name}」",
            color=COLORS["primary"],
        )

        # 基本資訊
        embed.add_field(
            name="❤️ 好感度", value=f"{affection}/1000 ({relationship_name})", inline=True
        )
        embed.add_field(name="🔮 種族", value=character.get_primary_race(), inline=True)
        embed.add_field(name="👗 體型", value=character.get_bust_description(), inline=True)

        # 屬性
        embed.add_field(
            name="💪 能力",
            value=(
                f"清掃: {character.abilities.cleaning} | "
                f"話術: {character.abilities.speech} | "
                f"戰鬥: {character.abilities.combat}"
            ),
            inline=False,
        )

        # 時間表
        visit_h = character.visit_time // 60
        leave_h = character.leave_time // 60
        embed.add_field(
            name="⏰ 活動時間", value=f"{visit_h:02d}:00 - {leave_h:02d}:00", inline=True
        )

        if character.occupation:
            embed.add_field(name="💼 工作", value=character.occupation[:50], inline=True)

        return embed

    @staticmethod
    def character_list(
        characters: list[tuple[Character, int]], page: int = 0, per_page: int = 10
    ) -> discord.Embed:
        """角色列表 Embed"""
        embed = discord.Embed(title="👥 角色列表", color=COLORS["info"])

        start_idx = page * per_page
        end_idx = start_idx + per_page
        page_chars = characters[start_idx:end_idx]

        if not page_chars:
            embed.description = "沒有找到角色"
            return embed

        lines = []
        for char, affection in page_chars:
            char_info = MVP_CHARACTERS.get(char.id, {"emoji": "👤"})
            emoji = char_info.get("emoji", "👤")
            lines.append(f"{emoji} **{char.callname}** - ❤️ {affection}")

        embed.description = "\n".join(lines)

        total_pages = (len(characters) + per_page - 1) // per_page
        embed.set_footer(text=f"頁面 {page + 1}/{total_pages}")

        return embed

    @staticmethod
    def command_result(
        character_name: str, message: str, affection_change: int, success: bool
    ) -> discord.Embed:
        """指令結果 Embed"""
        color = COLORS["success"] if success else COLORS["error"]

        embed = discord.Embed(title=f"與 {character_name} 的互動", description=message, color=color)

        if affection_change != 0:
            if affection_change > 0:
                embed.add_field(name="💕 好感度變化", value=f"+{affection_change}", inline=True)
            else:
                embed.add_field(name="💔 好感度變化", value=f"{affection_change}", inline=True)

        return embed

    @staticmethod
    def command_menu(character_name: str, available_categories: list[str]) -> discord.Embed:
        """指令選單 Embed"""
        embed = discord.Embed(
            title=f"📝 與 {character_name} 的互動",
            description="選擇一個指令類別：",
            color=COLORS["primary"],
        )

        category_emojis = {
            "日常": "☀️",
            "交流": "💬",
            "愛撫": "✋",
            "親密": "💕",
            "系統": "⚙️",
            "特殊": "⭐",
        }

        for cat in available_categories:
            emoji = category_emojis.get(cat, "📌")
            commands = COMMAND_CATEGORIES.get(cat, [])
            embed.add_field(name=f"{emoji} {cat}", value=f"{len(commands)} 個指令", inline=True)

        return embed

    @staticmethod
    def save_success(slot: int) -> discord.Embed:
        """存檔成功 Embed"""
        return discord.Embed(
            title="💾 存檔成功", description=f"遊戲已儲存至槽位 {slot}", color=COLORS["success"]
        )

    @staticmethod
    def new_game_welcome() -> discord.Embed:
        """新遊戲歡迎 Embed"""
        embed = discord.Embed(
            title="🌸 歡迎來到幻想鄉！",
            description=(
                "你來到了博麗神社，開始了在幻想鄉的新生活。\n\n"
                "在這裡，你可以與各種角色互動、建立關係...\n"
                "祝你玩得開心！"
            ),
            color=COLORS["primary"],
        )

        embed.add_field(
            name="💡 提示",
            value=(
                "• 使用「角色列表」查看可互動的角色\n"
                "• 使用「選擇角色」開始與某人互動\n"
                "• 累積好感度來解鎖更多互動選項"
            ),
            inline=False,
        )

        return embed

    @staticmethod
    def error(message: str) -> discord.Embed:
        """錯誤訊息 Embed"""
        return discord.Embed(title="❌ 錯誤", description=message, color=COLORS["error"])

    @staticmethod
    def info(title: str, message: str) -> discord.Embed:
        """資訊 Embed"""
        return discord.Embed(title=f"ℹ️ {title}", description=message, color=COLORS["info"])
