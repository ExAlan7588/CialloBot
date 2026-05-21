from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import user_bindings
from utils import user_data_manager
from utils.localization_text import format_translation, lookup_translation
from utils.osu_domain import calculate_accuracy, decode_mods
from utils.osu_http import OsuAPIDataError, api_v2_url, expect_dict, expect_list
from utils.user_binding_store import (
    load_bindings_from_json,
    serialize_user_bindings,
    validate_user_bindings,
)


def test_osu_http_url_and_response_shape_helpers() -> None:
    assert api_v2_url("users/1") == "https://osu.ppy.sh/api/v2/users/1"
    assert api_v2_url("/users/1") == "https://osu.ppy.sh/api/v2/users/1"
    assert expect_dict({"ok": True}, "ctx") == {"ok": True}
    assert expect_list(["ok"], "ctx") == ["ok"]

    with pytest.raises(OsuAPIDataError, match="Expected object response"):
        expect_dict([], "ctx")


def test_osu_domain_mods_and_accuracy_helpers() -> None:
    assert decode_mods(0) == "None"
    assert decode_mods(576) == "NC"
    assert decode_mods(["HD", "HR"]) == "HDHR"
    assert calculate_accuracy({"count_300": 300}, "osu") == 100.0
    assert calculate_accuracy({"accuracy": 0.9876}, "fruits") == 98.76


def test_localization_text_lookup_and_format_helpers() -> None:
    translations = {"en": {"hello": "Hello {name}"}, "zh_TW": {}}
    assert (
        lookup_translation(
            translations, lang_code="zh_TW", default_language="en", key="hello", default_fallback=""
        )
        == "Hello {name}"
    )
    assert (
        lookup_translation(
            translations,
            lang_code="zh_TW",
            default_language="en",
            key="missing",
            default_fallback="Fallback",
        )
        == "Fallback"
    )
    assert format_translation("Hello {name}", "hello", name="Ciallo") == "Hello Ciallo"
    assert format_translation("Hello {name}", "hello") == "Hello {name}"


def test_user_binding_store_helpers() -> None:
    assert load_bindings_from_json('{"123": "456"}', Path("bindings.json")) == {"123": "456"}
    assert validate_user_bindings(Path("bindings.json"), {"123": "456"}) == {"123": "456"}
    assert serialize_user_bindings({"123": "456"}).startswith("{")

    with pytest.raises(TypeError, match="invalid Discord user id key"):
        validate_user_bindings(Path("bindings.json"), {123: "456"})


def test_user_binding_service_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(user_data_manager, "DATA_FILE", tmp_path / "bindings.json")

    async def assert_round_trip() -> None:
        assert await user_bindings.bind_user(123, "456")
        assert await user_bindings.get_bound_user(123) == "456"
        assert await user_bindings.unbind_user(123)
        assert await user_bindings.get_bound_user(123) is None

    asyncio.run(assert_round_trip())
