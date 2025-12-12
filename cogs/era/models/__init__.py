# Era TW Data Models
"""資料模型"""

from .enums import (
    Gender,
    Relationship,
    CommandCategory,
    CharacterPersonality,
    Race,
    Location,
    TimeOfDay,
    Weather,
    GameState,
)
from .character import (
    Character,
    CharacterStats,
    CharacterAbilities,
    CharacterTalents,
    CharacterRelationship,
    MVP_CHARACTER_IDS,
)
from .player import PlayerSave, GameProgress, Inventory, MAX_SAVE_SLOTS
