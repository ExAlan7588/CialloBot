from __future__ import annotations


def format_mods_for_display(mod_list: list[str]) -> str:
    if not mod_list:
        return ""
    return "+" + "".join(mod_list).upper()
