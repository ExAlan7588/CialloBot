"""Era TW Discord UI Views

定義遊戲使用的 Discord 按鈕和選單視圖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Any

import discord
from discord import ButtonStyle, SelectOption
from discord.ui import View, Button, Select, button, select

from ..data.constants import MVP_CHARACTERS, COMMAND_CATEGORIES, COMMANDS
from ..models.character import Character

if TYPE_CHECKING:
    from ..managers.game_manager import GameManager
    from ..managers.character_manager import CharacterManager
    from ..managers.command_manager import CommandManager


class MainMenuView(View):
    """主選單視圖"""

    def __init__(
        self,
        discord_id: int,
        game_manager: "GameManager",
        character_manager: "CharacterManager",
        command_manager: "CommandManager",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.discord_id = discord_id
        self.game_manager = game_manager
        self.character_manager = character_manager
        self.command_manager = command_manager

    @button(label="👥 角色列表", style=ButtonStyle.primary, row=0)
    async def character_list_btn(self, interaction: discord.Interaction, btn: Button):
        """顯示角色列表"""
        from .embeds import EraEmbeds

        characters = self.character_manager.get_characters_by_affection(self.discord_id)
        embed = EraEmbeds.character_list(characters)

        view = CharacterSelectView(
            self.discord_id,
            self.game_manager,
            self.character_manager,
            self.command_manager,
            characters,
        )

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="📊 遊戲狀態", style=ButtonStyle.secondary, row=0)
    async def game_status_btn(self, interaction: discord.Interaction, btn: Button):
        """顯示遊戲狀態"""
        from .embeds import EraEmbeds

        save = self.game_manager.get_player_save(self.discord_id)
        if not save:
            await interaction.response.send_message(
                embed=EraEmbeds.error("找不到存檔"), ephemeral=True
            )
            return

        embed = EraEmbeds.main_menu(save)
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="💾 存檔", style=ButtonStyle.secondary, row=0)
    async def save_btn(self, interaction: discord.Interaction, btn: Button):
        """存檔"""
        from .embeds import EraEmbeds

        # TODO: 實作資料庫存檔
        embed = EraEmbeds.info("存檔", "存檔功能正在開發中...")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @button(label="❌ 結束", style=ButtonStyle.danger, row=0)
    async def quit_btn(self, interaction: discord.Interaction, btn: Button):
        """結束遊戲"""
        from .embeds import EraEmbeds

        embed = EraEmbeds.info("再見", "感謝遊玩！下次見～")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CharacterSelectView(View):
    """角色選擇視圖"""

    def __init__(
        self,
        discord_id: int,
        game_manager: "GameManager",
        character_manager: "CharacterManager",
        command_manager: "CommandManager",
        characters: list[tuple[Character, int]],
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.discord_id = discord_id
        self.game_manager = game_manager
        self.character_manager = character_manager
        self.command_manager = command_manager
        self.characters = characters

        # 添加角色選擇下拉選單
        self._add_character_select()

    def _add_character_select(self):
        """添加角色選擇選單"""
        options = []
        for char, affection in self.characters[:25]:  # Discord 限制 25 個選項
            char_info = MVP_CHARACTERS.get(char.id, {"emoji": "👤"})
            emoji = char_info.get("emoji", "👤")

            options.append(
                SelectOption(
                    label=char.callname,
                    value=str(char.id),
                    description=f"❤️ {affection}",
                    emoji=emoji,
                )
            )

        if options:
            select_menu = Select(
                placeholder="選擇一個角色...", options=options, custom_id="character_select"
            )
            select_menu.callback = self.on_character_select
            self.add_item(select_menu)

    async def on_character_select(self, interaction: discord.Interaction):
        """角色選擇回調"""
        from .embeds import EraEmbeds

        select_menu = interaction.data.get("values", [])
        if not select_menu:
            return

        char_id = int(select_menu[0])

        # 設置互動目標
        success, msg = self.game_manager.set_interaction_target(self.discord_id, char_id)
        if not success:
            await interaction.response.send_message(embed=EraEmbeds.error(msg), ephemeral=True)
            return

        # 顯示角色狀態和互動選單
        char = self.character_manager.get_character(char_id)
        if not char:
            return

        affection = self.character_manager.get_affection(self.discord_id, char_id)
        relationship = self.character_manager.get_relationship_name(self.discord_id, char_id)

        embed = EraEmbeds.character_status(char, affection, relationship)

        view = CommandSelectView(
            self.discord_id,
            char_id,
            self.game_manager,
            self.character_manager,
            self.command_manager,
        )

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="🔙 返回", style=ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, btn: Button):
        """返回主選單"""
        from .embeds import EraEmbeds

        save = self.game_manager.get_player_save(self.discord_id)
        if not save:
            return

        embed = EraEmbeds.main_menu(save)
        view = MainMenuView(
            self.discord_id, self.game_manager, self.character_manager, self.command_manager
        )

        await interaction.response.edit_message(embed=embed, view=view)


class CommandSelectView(View):
    """指令選擇視圖"""

    def __init__(
        self,
        discord_id: int,
        target_id: int,
        game_manager: "GameManager",
        character_manager: "CharacterManager",
        command_manager: "CommandManager",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.discord_id = discord_id
        self.target_id = target_id
        self.game_manager = game_manager
        self.character_manager = character_manager
        self.command_manager = command_manager

        # 添加指令類別選擇
        self._add_category_select()

    def _add_category_select(self):
        """添加指令類別選單"""
        options = [
            SelectOption(label="☀️ 日常", value="日常", description="日常交流指令"),
            SelectOption(label="💬 交流", value="交流", description="深入交流指令"),
            SelectOption(label="✋ 愛撫", value="愛撫", description="親密互動指令"),
            SelectOption(label="💕 親密", value="親密", description="進階親密指令"),
            SelectOption(label="⭐ 特殊", value="特殊", description="特殊指令"),
        ]

        select_menu = Select(
            placeholder="選擇指令類別...", options=options, custom_id="category_select"
        )
        select_menu.callback = self.on_category_select
        self.add_item(select_menu)

    async def on_category_select(self, interaction: discord.Interaction):
        """類別選擇回調"""
        select_values = interaction.data.get("values", [])
        if not select_values:
            return

        category = select_values[0]

        # 取得該類別的可用指令
        commands = self.command_manager.get_available_commands(self.discord_id, category)

        if not commands:
            from .embeds import EraEmbeds

            await interaction.response.send_message(
                embed=EraEmbeds.error("這個類別沒有可用的指令"), ephemeral=True
            )
            return

        # 創建指令選擇視圖
        view = CommandExecuteView(
            self.discord_id,
            self.target_id,
            commands,
            self.game_manager,
            self.character_manager,
            self.command_manager,
        )

        char = self.character_manager.get_character(self.target_id)
        name = char.callname if char else "對方"

        from .embeds import EraEmbeds

        embed = EraEmbeds.command_menu(name, [category])

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="🔙 返回", style=ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, btn: Button):
        """返回角色列表"""
        from .embeds import EraEmbeds

        # 結束互動
        self.game_manager.end_interaction(self.discord_id)

        characters = self.character_manager.get_characters_by_affection(self.discord_id)
        embed = EraEmbeds.character_list(characters)

        view = CharacterSelectView(
            self.discord_id,
            self.game_manager,
            self.character_manager,
            self.command_manager,
            characters,
        )

        await interaction.response.edit_message(embed=embed, view=view)


class CommandExecuteView(View):
    """指令執行視圖"""

    def __init__(
        self,
        discord_id: int,
        target_id: int,
        commands: list[tuple[int, str]],
        game_manager: "GameManager",
        character_manager: "CharacterManager",
        command_manager: "CommandManager",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.discord_id = discord_id
        self.target_id = target_id
        self.commands = commands
        self.game_manager = game_manager
        self.character_manager = character_manager
        self.command_manager = command_manager

        # 添加指令選擇
        self._add_command_select()

    def _add_command_select(self):
        """添加指令選單"""
        options = []
        for cmd_id, cmd_name in self.commands[:25]:
            options.append(SelectOption(label=cmd_name, value=str(cmd_id)))

        if options:
            select_menu = Select(
                placeholder="選擇一個指令...", options=options, custom_id="command_select"
            )
            select_menu.callback = self.on_command_select
            self.add_item(select_menu)

    async def on_command_select(self, interaction: discord.Interaction):
        """指令選擇回調"""
        from .embeds import EraEmbeds

        select_values = interaction.data.get("values", [])
        if not select_values:
            return

        cmd_id = int(select_values[0])

        # 執行指令
        result = await self.command_manager.execute_command(self.discord_id, cmd_id)

        char = self.character_manager.get_character(self.target_id)
        name = char.callname if char else "對方"

        embed = EraEmbeds.command_result(
            name, result.message, result.affection_change, result.success
        )

        # 更新視圖，允許繼續互動
        view = CommandSelectView(
            self.discord_id,
            self.target_id,
            self.game_manager,
            self.character_manager,
            self.command_manager,
        )

        await interaction.response.edit_message(embed=embed, view=view)

    @button(label="🔙 返回", style=ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, btn: Button):
        """返回指令類別"""
        from .embeds import EraEmbeds

        char = self.character_manager.get_character(self.target_id)
        if not char:
            return

        affection = self.character_manager.get_affection(self.discord_id, self.target_id)
        relationship = self.character_manager.get_relationship_name(self.discord_id, self.target_id)

        embed = EraEmbeds.character_status(char, affection, relationship)

        view = CommandSelectView(
            self.discord_id,
            self.target_id,
            self.game_manager,
            self.character_manager,
            self.command_manager,
        )

        await interaction.response.edit_message(embed=embed, view=view)
