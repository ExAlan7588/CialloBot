"""Era TW 格式化工具

提供各種格式化輸出的工具函數。
"""

from __future__ import annotations


def format_stats(stamina: int, max_stamina: int, energy: int, max_energy: int) -> str:
    """格式化基本狀態

    Args:
        stamina: 當前體力
        max_stamina: 最大體力
        energy: 當前氣力
        max_energy: 最大氣力

    Returns:
        格式化的狀態字串
    """
    stamina_bar = _create_bar(stamina, max_stamina)
    energy_bar = _create_bar(energy, max_energy)

    return (
        f"💪 體力: {stamina}/{max_stamina} {stamina_bar}\n"
        f"⚡ 氣力: {energy}/{max_energy} {energy_bar}"
    )


def format_abilities(cleaning: int, speech: int, combat: int, cooking: int, music: int) -> str:
    """格式化能力值

    Args:
        cleaning: 清掃技能
        speech: 話術技能
        combat: 戰鬥能力
        cooking: 料理技能
        music: 音樂技能

    Returns:
        格式化的能力字串
    """
    return (
        f"🧹 清掃: {_format_level(cleaning)} | "
        f"💬 話術: {_format_level(speech)} | "
        f"⚔️ 戰鬥: {_format_level(combat)}\n"
        f"🍳 料理: {_format_level(cooking)} | "
        f"🎵 音樂: {_format_level(music)}"
    )


def format_affection(affection: int, max_affection: int = 1000) -> str:
    """格式化好感度

    Args:
        affection: 當前好感度
        max_affection: 最大好感度

    Returns:
        格式化的好感度字串
    """
    bar = _create_bar(affection, max_affection, 10)
    percentage = int(affection / max_affection * 100)

    if affection >= 900:
        emoji = "💕"
        level = "戀人"
    elif affection >= 700:
        emoji = "💗"
        level = "親密"
    elif affection >= 500:
        emoji = "💖"
        level = "好友"
    elif affection >= 300:
        emoji = "❤️"
        level = "朋友"
    elif affection >= 100:
        emoji = "🧡"
        level = "認識"
    else:
        emoji = "💔"
        level = "陌生"

    return f"{emoji} {affection}/{max_affection} ({level}) {bar}"


def format_time(minutes: int) -> str:
    """格式化遊戲時間

    Args:
        minutes: 分鐘數（從午夜開始）

    Returns:
        格式化的時間字串 (HH:MM)
    """
    hours = (minutes // 60) % 24
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def format_day_time(day: int, minutes: int) -> str:
    """格式化日期和時間

    Args:
        day: 遊戲天數
        minutes: 分鐘數

    Returns:
        格式化的日期時間字串
    """
    time_str = format_time(minutes)

    # 判斷時段
    hour = minutes // 60
    if 4 <= hour < 6:
        period = "🌅 黎明"
    elif 6 <= hour < 12:
        period = "☀️ 早晨"
    elif 12 <= hour < 18:
        period = "🌤️ 下午"
    elif 18 <= hour < 20:
        period = "🌆 傍晚"
    else:
        period = "🌙 夜晚"

    return f"第 {day} 天 {time_str} ({period})"


def format_money(amount: int) -> str:
    """格式化金錢

    Args:
        amount: 金額

    Returns:
        格式化的金錢字串
    """
    return f"💰 {amount:,}"


def _create_bar(
    current: int, maximum: int, length: int = 10, fill_char: str = "█", empty_char: str = "░"
) -> str:
    """創建進度條

    Args:
        current: 當前值
        maximum: 最大值
        length: 進度條長度
        fill_char: 填充字符
        empty_char: 空白字符

    Returns:
        進度條字串
    """
    if maximum <= 0:
        return empty_char * length

    ratio = min(max(current / maximum, 0), 1)
    filled = int(ratio * length)
    empty = length - filled

    return fill_char * filled + empty_char * empty


def _format_level(level: int) -> str:
    """格式化等級顯示

    Args:
        level: 等級值

    Returns:
        格式化的等級字串
    """
    if level >= 5:
        return f"★★★ ({level})"
    elif level >= 3:
        return f"★★☆ ({level})"
    elif level >= 1:
        return f"★☆☆ ({level})"
    else:
        return f"☆☆☆ ({level})"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截斷過長的文字

    Args:
        text: 原始文字
        max_length: 最大長度
        suffix: 截斷後綴

    Returns:
        截斷後的文字
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
