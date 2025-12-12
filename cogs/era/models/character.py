"""Era TW 角色模型

定義角色資料結構，對應 eraTW 的 CSV/Chara/*.csv 檔案格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .enums import Gender, Race, CharacterPersonality


@dataclass
class CharacterStats:
    """角色基礎屬性

    對應 CSV 中的「基礎」欄位
    """

    stamina: int = 2000  # 体力
    max_stamina: int = 2000
    energy: int = 1500  # 气力
    max_energy: int = 1500
    lust: int = 0  # 勃起/情欲度
    max_lust: int = 1500
    vitality: int = 10000  # 精力
    max_vitality: int = 10000
    mana: int = 4000  # 法力
    max_mana: int = 4000
    mood: int = 1500  # 情绪
    max_mood: int = 1500
    reason: int = 1000  # 理性
    max_reason: int = 1000
    anger: int = 0  # 愤怒
    max_anger: int = 1000
    depth: int = 1000  # 深度
    alcohol: int = 0  # 酒气
    max_alcohol: int = 1900


@dataclass
class CharacterAbilities:
    """角色能力值 (ABL)

    對應 CSV/Abl.csv 和角色 CSV 中的「能力」欄位
    """

    # 感覺系
    c_sensitivity: int = 0  # C感觉 (0)
    v_sensitivity: int = 0  # V感觉 (1)
    a_sensitivity: int = 0  # A感觉 (2)
    b_sensitivity: int = 0  # B感觉 (3)
    m_sensitivity: int = 0  # M感觉 (4)

    # 基本屬性
    intimacy: int = 0  # 亲密 (9)
    obedience: int = 0  # 顺从 (10)
    desire: int = 0  # 欲望 (11)
    technique: int = 0  # 技巧 (12)
    service_spirit: int = 0  # 侍奉精神 (13)
    exhibitionism: int = 0  # 露出癖 (14)
    masochism: int = 0  # 受虐属性 (15)
    sadism: int = 0  # 施虐属性 (16)
    yuri: int = 0  # 百合属性 (17)
    yaoi: int = 0  # 断袖属性 (18)

    # 技能
    cleaning: int = 0  # 清扫技能 (40)
    speech: int = 0  # 话术技能 (41)
    combat: int = 0  # 战斗能力 (42)
    culture: int = 0  # 教养 (43)
    cooking: int = 0  # 料理技能 (44)
    music: int = 0  # 音乐技能 (45)

    # 性技
    finger_skill: int = 0  # 指 (50)
    tongue_skill: int = 0  # 舌 (51)
    chest_skill: int = 0  # 胸 (52)
    waist_skill: int = 0  # 腰 (53)
    v_skill: int = 0  # 膣 (54)
    a_skill: int = 0  # 肛门 (55)


@dataclass
class CharacterTalents:
    """角色天賦 (Talent)

    對應 CSV/Talent.csv 和角色 CSV 中的「素質」欄位
    """

    # 基本天賦
    virgin: int = 0  # 处女 (0): 1=处女, 2=再生处女, -1=无自觉非处女
    non_virgin: int = 0  # 非童贞 (1)
    gender: int = 1  # 性别 (2): 1=女, 2=男, 3=扶她

    # 陷落狀態
    love: int = 0  # 恋慕 (3)
    lewd: int = 0  # 淫乱 (4)
    submission: int = 0  # 服从 (5)
    no_kiss_exp: int = 1  # 无接吻经验 (6)
    lover: int = 0  # 恋人 (7)

    # 性格
    courage: int = 0  # 胆量 (10): -1=胆怯, 1=坚强
    attitude: int = 0  # 态度 (11): -1=坦率, 1=叛逆
    response: int = 0  # 回应 (12): -1=老实, 1=傲慢
    pride: int = 0  # 自尊心 (13): -1=低, 1=高
    tsundere: int = 0  # 傲娇 (14)
    mood_var: int = 0  # 心情 (15)
    appearance: int = 0  # 容姿 (16): -1=丑恶, 1=容姿端丽
    age: int = 0  # 年龄 (17): -1=儿童, 0=青年, 1=中年, 2=老人

    # 身體特徵
    body_type: int = 0  # 体型 (100): -5=小人, -2=幼儿, -1=矮小, 1=长身, 2=巨躯
    bust_size: int = 0  # 胸围 (105): -2=绝壁, -1=贫乳, 0=并乳, 1=巨乳, 2=爆乳
    alcohol_tolerance: int = 0  # 酒耐性 (121)

    # 種族
    human: int = 0  # 人类 (190)
    youkai: int = 0  # 妖怪 (191)
    fairy: int = 0  # 妖精 (192)
    spirit: int = 0  # 神灵 (193)
    ghost: int = 0  # 幽灵 (194)
    tsukumogami: int = 0  # 付丧神 (195)
    doll: int = 0  # 人形 (196)
    extra_race: int = 0  # 追加种族 (197): 1=巫女, 2=魔法使, 3=女仆, 4=蓬莱人

    # 特殊
    pregnancy: int = 0  # 妊娠 (153)
    child_rearing: int = 0  # 育儿中 (154)


@dataclass
class CharacterRelationship:
    """角色關係資料"""

    affection: int = 0  # 好感度
    trust: int = 0  # 信頼度
    lust_towards: int = 0  # 對玩家的慾望
    times_together: int = 0  # 一起過夜次數
    confession_count: int = 0  # 告白次數
    is_lover: bool = False  # 是否為戀人


@dataclass
class Character:
    """角色完整資料

    對應 eraTW 的 CSV/Chara/CharaX_Name.csv 檔案
    """

    # 基本資訊
    id: int  # 番号
    name: str  # 名前 (日文名)
    callname: str  # 呼び名 (稱呼)

    # 屬性群組
    stats: CharacterStats = field(default_factory=CharacterStats)
    abilities: CharacterAbilities = field(default_factory=CharacterAbilities)
    talents: CharacterTalents = field(default_factory=CharacterTalents)
    relationship: CharacterRelationship = field(default_factory=CharacterRelationship)

    # 位置與狀態
    current_location: int = 0  # 当前位置
    home_location: int = 0  # 自宅位置

    # 時間表
    visit_time: int = 540  # 来访时间 (預設9:00)
    leave_time: int = 1140  # 回家时间 (預設19:00)
    sleep_time: int = 1380  # 就寝时间 (預設23:00)
    wake_time: int = 360  # 起床时间 (預設6:00)

    # 相性（與其他角色的關係）
    compatibility: dict[int, int] = field(default_factory=dict)

    # 額外資訊
    description: str = ""  # 角色描述
    occupation: str = ""  # 工作情报

    # 遊戲狀態旗標
    flags: dict[str, int] = field(default_factory=dict)

    def is_available(self, current_time: int) -> bool:
        """檢查角色在指定時間是否可互動"""
        if self.visit_time <= self.leave_time:
            return self.visit_time <= current_time <= self.leave_time
        else:
            return current_time >= self.visit_time or current_time <= self.leave_time

    def get_primary_race(self) -> str:
        """取得角色的主要種族"""
        if self.talents.human > 0:
            races = {1: "人類", 2: "仙人", 3: "天人", 4: "月人", 5: "魔界人", 6: "外界人"}
            return races.get(self.talents.human, "人類")
        if self.talents.youkai > 0:
            races = {
                1: "妖怪",
                2: "鬼",
                3: "吸血鬼",
                4: "河童",
                5: "天狗",
                6: "妖獸",
                7: "妖鳥",
                8: "妖蟲",
                9: "惡魔",
            }
            return races.get(self.talents.youkai, "妖怪")
        if self.talents.fairy > 0:
            return "妖精"
        if self.talents.spirit > 0:
            races = {1: "神靈", 2: "死神", 3: "閻魔"}
            return races.get(self.talents.spirit, "神靈")
        if self.talents.ghost > 0:
            return "幽靈"
        return "不明"

    def get_bust_description(self) -> str:
        """取得胸圍描述"""
        bust_map = {-2: "绝壁", -1: "贫乳", 0: "普通", 1: "巨乳", 2: "爆乳"}
        return bust_map.get(self.talents.bust_size, "普通")


# MVP 優先角色 ID 列表
MVP_CHARACTER_IDS = [
    1,  # 博丽 灵梦
    11,  # 魔理沙
    15,  # 咲夜
    16,  # 蕾米莉亚
    50,  # 芙兰
    26,  # 紫
    23,  # 妖梦
    31,  # 早苗
    38,  # 恋 (こいし)
    54,  # 帕秋莉
]
