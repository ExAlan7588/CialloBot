from __future__ import annotations

OSU_MODES_INT_TO_STRING = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}
OSU_MODES_STRING_TO_INT = {value: key for key, value in OSU_MODES_INT_TO_STRING.items()}

OSU_MODES_L10N_KEYS = {0: "mode_std", 1: "mode_taiko", 2: "mode_ctb", 3: "mode_mania"}
OSU_MODES_NAME_ONLY_L10N_KEYS = {
    0: "mode_name_only_std",
    1: "mode_name_only_taiko",
    2: "mode_name_only_ctb",
    3: "mode_name_only_mania",
}

MODE_EMOJI_STRINGS = {
    0: "<:std:1373198119361318932>",
    1: "<:taiko:1373198130006200370>",
    2: "<:ctb:1373198138751320104>",
    3: "<:mania:1373198147056304139>",
}
MODE_FALLBACK_TEXT = {0: "osu!", 1: "Taiko", 2: "Catch", 3: "Mania"}

RECENT_SCORE_LIMIT = 50
BEST_SCORE_LIMIT = 200
ERROR_DETAIL_LIMIT = 100
BP_RANK_INPUT_MAX_LENGTH = 3
SCORE_VIEW_TIMEOUT_SECONDS = 300

RANK_COLORS = {
    "XH": 0xAAAAFF,
    "X": 0xFFD700,
    "SH": 0xC0C0C0,
    "S": 0xFFE4B5,
    "A": 0x7FFF00,
    "B": 0xFFC0CB,
    "C": 0xFF0000,
    "D": 0x808080,
    "F": 0x000000,
}

RANK_EMOJI_MAP = {
    "XH": "<:rkhdfl:1373246417350561844>",
    "X": "<:rkss:1373246926379679836>",
    "SH": "<:rkhdfl:1373246417350561844>",
    "S": "<:rks:1373246734079230072>",
    "A": "<:rka:1373246979211132988>",
    "B": "<:rkb:1373247010169159721>",
    "C": "<:rkc:1373247035268006010>",
    "D": "<:rkd:1373247061360644187>",
}

RANK_XH_EMOJI = "<:rkhdfl:1373246417350561844>"
RANK_SH_EMOJI = "<:rkshdfl:1373964175671427143>"
RANK_HD_FL_SS_EMOJI = "<:rkhdflss:1373246464522653727>"
