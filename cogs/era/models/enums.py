"""Era TW 枚舉定義

定義遊戲中使用的各種枚舉類型。
"""

from __future__ import annotations

from enum import IntEnum, IntFlag, auto


class Gender(IntEnum):
    """性別

    對應 CSV 中的 素質,性别 欄位：
    1=女性器 2=男性器 3=扶她
    """

    NONE = 0
    FEMALE = 1  # 女性
    MALE = 2  # 男性
    FUTANARI = 3  # 扶她


class Relationship(IntEnum):
    """關係狀態"""

    STRANGER = 0  # 陌生人
    ACQUAINTANCE = 1  # 認識
    FRIEND = 2  # 朋友
    CLOSE_FRIEND = 3  # 親密朋友
    LOVER = 4  # 戀人
    SPOUSE = 5  # 配偶


class CommandCategory(IntEnum):
    """指令類別

    對應 Train.csv 中的指令分類
    """

    CARESS = 0  # 愛撫系 (0-19)
    COMMUNICATION = 1  # 交流系 (20-30)
    TOOL = 2  # 道具系 (40-55)
    POSITION = 3  # 體位系 (60-99)
    SM = 4  # SM系 (100-150)
    ORAL = 5  # 口交系 (80-99)
    DAILY = 6  # 日常系 (300-500)
    DATING = 7  # 約會系 (600-699)
    SPECIAL = 8  # 特殊指令


class CharacterPersonality(IntFlag):
    """角色性格旗標

    對應 Talent.csv 中的性格相關天賦
    """

    NONE = 0
    BRAVE = auto()  # 胆量: 坚强
    TIMID = auto()  # 胆量: 胆怯
    HONEST = auto()  # 态度: 坦率
    REBELLIOUS = auto()  # 态度: 叛逆
    OBEDIENT = auto()  # 回应: 老实
    ARROGANT = auto()  # 回应: 傲慢
    LOW_PRIDE = auto()  # 自尊心低
    HIGH_PRIDE = auto()  # 自尊心高
    TSUNDERE = auto()  # 傲娇
    CHEERFUL = auto()  # 开朗
    GLOOMY = auto()  # 阴郁


class Race(IntEnum):
    """種族類型

    對應 Talent.csv 中的種族天賦 (190-197)
    """

    UNKNOWN = 0
    HUMAN = 1  # 人类
    YOUKAI = 2  # 妖怪
    FAIRY = 3  # 妖精
    SPIRIT = 4  # 神灵
    GHOST = 5  # 幽灵
    TSUKUMOGAMI = 6  # 付丧神
    DOLL = 7  # 人形
    VAMPIRE = 8  # 吸血鬼
    ONI = 9  # 鬼
    TENGU = 10  # 天狗
    KAPPA = 11  # 河童


class Location(IntEnum):
    """場景位置

    遊戲中的主要場景
    """

    HAKUREI_SHRINE = 0  # 博麗神社
    SCARLET_MANOR = 1  # 紅魔館
    HUMAN_VILLAGE = 2  # 人間之里
    BAMBOO_FOREST = 3  # 迷途竹林
    YOUKAI_MOUNTAIN = 4  # 妖怪之山
    MORIYA_SHRINE = 5  # 守矢神社
    NETHERWORLD = 6  # 冥界
    EIENTEI = 7  # 永遠亭
    MYOUREN_TEMPLE = 8  # 命蓮寺
    UNDERGROUND = 9  # 地底


class TimeOfDay(IntEnum):
    """時間段"""

    DAWN = 0  # 黎明 (4:00-6:00)
    MORNING = 1  # 早晨 (6:00-12:00)
    AFTERNOON = 2  # 下午 (12:00-18:00)
    EVENING = 3  # 傍晚 (18:00-20:00)
    NIGHT = 4  # 夜晚 (20:00-4:00)


class Weather(IntEnum):
    """天氣"""

    SUNNY = 0  # 晴天
    CLOUDY = 1  # 陰天
    RAINY = 2  # 雨天
    SNOWY = 3  # 下雪
    FOGGY = 4  # 霧天
    STORMY = 5  # 暴風雨


class GameState(IntEnum):
    """遊戲狀態"""

    IDLE = 0  # 閒置（主選單）
    EXPLORING = 1  # 探索中
    INTERACTING = 2  # 互動中（訓練模式）
    DATING = 3  # 約會中
    BATTLE = 4  # 戰鬥中
    SLEEPING = 5  # 陪睡中
