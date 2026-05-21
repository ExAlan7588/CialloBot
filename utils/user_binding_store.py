from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from pathlib import Path

UserBindings: TypeAlias = dict[str, str]


def load_bindings_from_json(content: str, path: Path) -> UserBindings:
    data = json.loads(content)
    if not isinstance(data, dict):
        msg = f"{path} must contain a JSON object"
        raise TypeError(msg)
    return validate_user_bindings(path, data)


def validate_user_bindings(path: Path, data: dict[object, object]) -> UserBindings:
    bindings: UserBindings = {}
    for discord_id, osu_user in data.items():
        if not isinstance(discord_id, str) or not discord_id:
            msg = f"{path} contains an invalid Discord user id key: {discord_id!r}"
            raise TypeError(msg)
        if not isinstance(osu_user, str) or not osu_user:
            msg = f"{path} contains an invalid osu! binding for Discord user {discord_id!r}"
            raise TypeError(msg)
        bindings[discord_id] = osu_user
    return bindings


def serialize_user_bindings(data: UserBindings) -> str:
    return json.dumps(data, indent=4, ensure_ascii=False)
