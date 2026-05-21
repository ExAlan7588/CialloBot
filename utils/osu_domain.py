from __future__ import annotations

from typing import Any

MANIA_MAX_HIT_VALUE = 320
OSU_MAX_HIT_VALUE = 300
OSU_GOOD_HIT_VALUE = 100
OSU_MEH_HIT_VALUE = 50
MANIA_KATU_HIT_VALUE = 200
TAIKO_GOOD_WEIGHT = 0.5

RULESET_IDS = {"osu": 0, "taiko": 1, "fruits": 2, "mania": 3}

MODS_ENUM = {
    1: "NF",
    2: "EZ",
    4: "TD",
    8: "HD",
    16: "HR",
    32: "SD",
    64: "DT",
    128: "RX",
    256: "HT",
    512: "NC",
    1024: "FL",
    2048: "AU",
    4096: "SO",
    8192: "AP",
    16384: "PF",
}

SPEED_MODS = {"NC", "DT", "HT"}


def decode_mods(mods_int: int | list[str]) -> str:
    if isinstance(mods_int, list):
        return "".join(mods_int) if mods_int else "None"
    if not isinstance(mods_int, int):
        return "Invalid"
    if mods_int == 0:
        return "None"

    mods = _decode_speed_mods(mods_int)
    mods.extend(mod for value, mod in MODS_ENUM.items() if mod not in SPEED_MODS and mods_int & value)
    return "".join(mods) if mods else "None"


def calculate_accuracy(statistics: dict[str, Any], mode: str = "osu") -> float:
    counts = _score_counts(statistics)
    if mode == "osu":
        return _calculate_osu_accuracy(counts)
    if mode == "taiko":
        return _calculate_taiko_accuracy(counts)
    if mode == "fruits":
        return _direct_accuracy(statistics)
    if mode == "mania":
        return _calculate_mania_accuracy(counts)
    return _direct_accuracy(statistics)


def _decode_speed_mods(mods_int: int) -> list[str]:
    if mods_int & 512:
        return ["NC"]
    if mods_int & 64:
        return ["DT"]
    if mods_int & 256:
        return ["HT"]
    return []


def _score_counts(statistics: dict[str, Any]) -> dict[str, int]:
    return {
        "c300": int(statistics.get("count_300", 0)),
        "c100": int(statistics.get("count_100", 0)),
        "c50": int(statistics.get("count_50", 0)),
        "miss": int(statistics.get("count_miss", 0)),
        "geki": int(statistics.get("count_geki", 0)),
        "katu": int(statistics.get("count_katu", 0)),
    }


def _calculate_osu_accuracy(counts: dict[str, int]) -> float:
    total_hits = counts["c300"] + counts["c100"] + counts["c50"] + counts["miss"]
    if total_hits == 0:
        return 0.0
    score = (
        counts["c300"] * OSU_MAX_HIT_VALUE
        + counts["c100"] * OSU_GOOD_HIT_VALUE
        + counts["c50"] * OSU_MEH_HIT_VALUE
    )
    return round(score / (total_hits * OSU_MAX_HIT_VALUE) * 100, 2)


def _calculate_taiko_accuracy(counts: dict[str, int]) -> float:
    total_hits = counts["c300"] + counts["c100"] + counts["miss"]
    if total_hits == 0:
        return 0.0
    return round((counts["c300"] + counts["c100"] * TAIKO_GOOD_WEIGHT) / total_hits * 100, 2)


def _calculate_mania_accuracy(counts: dict[str, int]) -> float:
    total_notes = sum(counts.values())
    if total_notes == 0:
        return 0.0
    score = (
        counts["geki"] * MANIA_MAX_HIT_VALUE
        + counts["c300"] * OSU_MAX_HIT_VALUE
        + counts["katu"] * MANIA_KATU_HIT_VALUE
        + counts["c100"] * OSU_GOOD_HIT_VALUE
        + counts["c50"] * OSU_MEH_HIT_VALUE
    )
    return round(score / (total_notes * MANIA_MAX_HIT_VALUE) * 100, 2)


def _direct_accuracy(statistics: dict[str, Any]) -> float:
    accuracy = statistics.get("accuracy")
    return float(accuracy) * 100 if accuracy is not None else 0.0
