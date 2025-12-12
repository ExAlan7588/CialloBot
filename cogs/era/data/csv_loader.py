"""Era TW CSV 資料載入器

解析 eraTW 的 CSV 資料檔案，轉換為 Python 資料結構。
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any

from loguru import logger

from ..models.character import (
    Character,
    CharacterAbilities,
    CharacterRelationship,
    CharacterStats,
    CharacterTalents,
    MVP_CHARACTER_IDS,
)


class CSVLoader:
    """CSV 資料載入器

    負責解析 eraTW 的 CSV 檔案並轉換為遊戲資料。
    """

    def __init__(self, era_path: str | Path):
        """初始化載入器

        Args:
            era_path: eraTW 遊戲資料夾路徑
        """
        self.era_path = Path(era_path)
        self.csv_path = self.era_path / "CSV"
        self.chara_path = self.csv_path / "Chara"

        # 快取
        self._abilities_def: dict[int, str] = {}
        self._talents_def: dict[int, str] = {}
        self._commands_def: dict[int, str] = {}
        self._items_def: dict[int, str] = {}
        self._characters: dict[int, Character] = {}

    def load_all(self, mvp_only: bool = True) -> None:
        """載入所有資料

        Args:
            mvp_only: 是否只載入 MVP 角色
        """
        logger.info("開始載入 eraTW 資料...")

        # 載入定義檔
        self._load_abilities()
        self._load_talents()
        self._load_commands()
        self._load_items()

        # 載入角色
        self._load_characters(mvp_only=mvp_only)

        logger.info(f"資料載入完成：{len(self._characters)} 個角色")

    def _read_csv(self, filepath: Path, encoding: str = "utf-8-sig") -> list[list[str]]:
        """讀取 CSV 檔案

        Args:
            filepath: CSV 檔案路徑
            encoding: 檔案編碼

        Returns:
            CSV 內容列表
        """
        rows = []
        try:
            with open(filepath, newline="", encoding=encoding) as f:
                reader = csv.reader(f)
                for row in reader:
                    # 跳過空行和註解行
                    if not row or (row[0].startswith(";") or row[0].startswith("#")):
                        continue
                    rows.append(row)
        except FileNotFoundError:
            logger.warning(f"找不到檔案: {filepath}")
        except Exception as e:
            logger.error(f"讀取 CSV 失敗 {filepath}: {e}")

        return rows

    def _load_abilities(self) -> None:
        """載入能力定義 (Abl.csv)"""
        filepath = self.csv_path / "Abl.csv"
        rows = self._read_csv(filepath)

        for row in rows:
            if len(row) >= 2:
                try:
                    abl_id = int(row[0])
                    abl_name = row[1].split(";")[0].strip()  # 移除註解
                    self._abilities_def[abl_id] = abl_name
                except ValueError:
                    continue

        logger.debug(f"載入 {len(self._abilities_def)} 個能力定義")

    def _load_talents(self) -> None:
        """載入天賦定義 (Talent.csv)"""
        filepath = self.csv_path / "Talent.csv"
        rows = self._read_csv(filepath)

        for row in rows:
            if len(row) >= 2:
                try:
                    talent_id = int(row[0])
                    talent_name = row[1].split(";")[0].strip()
                    self._talents_def[talent_id] = talent_name
                except ValueError:
                    continue

        logger.debug(f"載入 {len(self._talents_def)} 個天賦定義")

    def _load_commands(self) -> None:
        """載入指令定義 (Train.csv)"""
        filepath = self.csv_path / "Train.csv"
        rows = self._read_csv(filepath)

        for row in rows:
            if len(row) >= 2:
                try:
                    cmd_id = int(row[0])
                    cmd_name = row[1].split(";")[0].strip()
                    self._commands_def[cmd_id] = cmd_name
                except ValueError:
                    continue

        logger.debug(f"載入 {len(self._commands_def)} 個指令定義")

    def _load_items(self) -> None:
        """載入道具定義 (Item.csv)"""
        filepath = self.csv_path / "Item.csv"
        rows = self._read_csv(filepath)

        for row in rows:
            if len(row) >= 2:
                try:
                    item_id = int(row[0])
                    item_name = row[1].split(";")[0].strip()
                    self._items_def[item_id] = item_name
                except ValueError:
                    continue

        logger.debug(f"載入 {len(self._items_def)} 個道具定義")

    def _load_characters(self, mvp_only: bool = True) -> None:
        """載入角色資料

        Args:
            mvp_only: 是否只載入 MVP 角色
        """
        if not self.chara_path.exists():
            logger.error(f"角色資料夾不存在: {self.chara_path}")
            return

        # 遍歷所有角色 CSV 檔案
        for filepath in self.chara_path.glob("Chara*.csv"):
            try:
                # 從檔名提取角色 ID
                match = re.match(r"Chara(\d+)", filepath.stem)
                if not match:
                    continue

                char_id = int(match.group(1))

                # MVP 模式下只載入特定角色
                if mvp_only and char_id not in MVP_CHARACTER_IDS:
                    continue

                character = self._parse_character_csv(filepath, char_id)
                if character:
                    self._characters[char_id] = character

            except Exception as e:
                logger.error(f"載入角色失敗 {filepath}: {e}")

        logger.info(f"載入 {len(self._characters)} 個角色")

    def _parse_character_csv(self, filepath: Path, char_id: int) -> Character | None:
        """解析單個角色 CSV 檔案

        Args:
            filepath: CSV 檔案路徑
            char_id: 角色 ID

        Returns:
            Character 物件或 None
        """
        rows = self._read_csv(filepath)
        if not rows:
            return None

        # 初始化角色資料
        name = ""
        callname = ""
        stats = CharacterStats()
        abilities = CharacterAbilities()
        talents = CharacterTalents()

        # 額外資料
        visit_time = 540
        leave_time = 1140
        sleep_time = 1380
        wake_time = 360
        home_location = 0
        compatibility: dict[int, int] = {}
        description = ""
        occupation = ""
        flags: dict[str, int] = {}

        for row in rows:
            if len(row) < 2:
                continue

            key = row[0].strip()
            value = row[1].strip() if len(row) > 1 else ""
            extra = row[2].strip() if len(row) > 2 else ""

            # 基本資訊
            if key == "番号":
                pass  # 已從檔名取得
            elif key == "名前":
                name = value
            elif key == "呼び名":
                callname = value

            # 基礎屬性
            elif key == "基礎":
                self._parse_stat(value, extra, stats)

            # 能力
            elif key == "能力":
                self._parse_ability(value, extra, abilities)

            # 素質（天賦）
            elif key == "素質":
                self._parse_talent(value, extra, talents)

            # 旗標
            elif key == "フラグ":
                if value == "来访时间":
                    visit_time = int(extra.split(";")[0])
                elif value == "回家时间":
                    leave_time = int(extra.split(";")[0])
                elif value == "就寝时间":
                    sleep_time = int(extra.split(";")[0])
                elif value == "起床时间":
                    wake_time = int(extra.split(";")[0])
                elif value == "自宅位置":
                    home_location = int(extra.split(";")[0])
                else:
                    try:
                        flags[value] = int(extra.split(";")[0])
                    except ValueError:
                        pass

            # 相性
            elif key == "相性":
                try:
                    target_id = int(value)
                    compat_value = int(extra.split(";")[0])
                    compatibility[target_id] = compat_value
                except ValueError:
                    pass

            # 字串資料
            elif key == "CSTR":
                if value == "工作情报":
                    occupation = extra
                elif value == "10":
                    description = extra

        return Character(
            id=char_id,
            name=name,
            callname=callname,
            stats=stats,
            abilities=abilities,
            talents=talents,
            relationship=CharacterRelationship(),
            current_location=home_location,
            home_location=home_location,
            visit_time=visit_time,
            leave_time=leave_time,
            sleep_time=sleep_time,
            wake_time=wake_time,
            compatibility=compatibility,
            description=description,
            occupation=occupation,
            flags=flags,
        )

    def _parse_stat(self, stat_name: str, value: str, stats: CharacterStats) -> None:
        """解析基礎屬性"""
        try:
            val = int(value.split(";")[0])
        except ValueError:
            return

        stat_map = {
            "体力": ("stamina", "max_stamina"),
            "气力": ("energy", "max_energy"),
            "勃起": ("lust", "max_lust"),
            "精力": ("vitality", "max_vitality"),
            "法力": ("mana", "max_mana"),
            "情绪": ("mood", "max_mood"),
            "理性": ("reason", "max_reason"),
            "愤怒": ("anger",),
            "深度": ("depth",),
            "酒气": ("max_alcohol",),
        }

        if stat_name in stat_map:
            for attr in stat_map[stat_name]:
                setattr(stats, attr, val)

    def _parse_ability(self, abl_name: str, value: str, abilities: CharacterAbilities) -> None:
        """解析能力值"""
        try:
            val = int(value.split(";")[0])
        except ValueError:
            return

        abl_map = {
            "清扫技能": "cleaning",
            "话术技能": "speech",
            "战斗能力": "combat",
            "教养": "culture",
            "料理技能": "cooking",
            "音乐技能": "music",
        }

        if abl_name in abl_map:
            setattr(abilities, abl_map[abl_name], val)

    def _parse_talent(self, talent_name: str, value: str, talents: CharacterTalents) -> None:
        """解析天賦"""
        try:
            val = int(value.split(";")[0])
        except ValueError:
            return

        talent_map = {
            "处女": "virgin",
            "性别": "gender",
            "恋慕": "love",
            "淫乱": "lewd",
            "服从": "submission",
            "胆量": "courage",
            "态度": "attitude",
            "回应": "response",
            "自尊心": "pride",
            "傲娇": "tsundere",
            "容姿": "appearance",
            "年龄": "age",
            "体型": "body_type",
            "胸围": "bust_size",
            "酒耐性": "alcohol_tolerance",
            "人类": "human",
            "妖怪": "youkai",
            "妖精": "fairy",
            "神灵": "spirit",
            "幽灵": "ghost",
            "付丧神": "tsukumogami",
            "人形": "doll",
            "追加种族": "extra_race",
            "开朗／阴郁": "mood_var",
            "难以越过的底线": "courage",  # 特殊處理
            "贞操": "virgin",  # 映射到相關屬性
            "痛觉": "response",
            "谜之魅力": "appearance",
        }

        if talent_name in talent_map:
            setattr(talents, talent_map[talent_name], val)

    # 公開介面
    @property
    def abilities(self) -> dict[int, str]:
        """取得能力定義"""
        return self._abilities_def.copy()

    @property
    def talents(self) -> dict[int, str]:
        """取得天賦定義"""
        return self._talents_def.copy()

    @property
    def commands(self) -> dict[int, str]:
        """取得指令定義"""
        return self._commands_def.copy()

    @property
    def items(self) -> dict[int, str]:
        """取得道具定義"""
        return self._items_def.copy()

    @property
    def characters(self) -> dict[int, Character]:
        """取得角色資料"""
        return self._characters.copy()

    def get_character(self, char_id: int) -> Character | None:
        """取得指定角色"""
        return self._characters.get(char_id)

    def get_command_name(self, cmd_id: int) -> str:
        """取得指令名稱"""
        return self._commands_def.get(cmd_id, f"指令{cmd_id}")
