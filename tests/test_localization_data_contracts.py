from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from utils import localization
from utils import user_data_manager


@pytest.fixture(autouse=True)
def reset_localization_state() -> None:
    setattr(localization.config, "DEFAULT_LANGUAGE", "en")
    setattr(
        localization.config,
        "SUPPORTED_LANGUAGES",
        {"en": "English", "zh_TW": "Traditional Chinese"},
    )
    localization._replace_user_preferences({})
    localization._translations.clear()


def test_missing_user_preferences_file_initializes_empty_preferences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(localization, "USER_PREFS_FILE", tmp_path / "missing.json")
    localization._replace_user_preferences({"123": "zh_TW"})

    localization._load_user_preferences()

    assert localization.get_user_language("123") == "en"


def test_empty_user_preferences_file_raises_explicit_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prefs_path = tmp_path / "prefs.json"
    prefs_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(localization, "USER_PREFS_FILE", prefs_path)

    with pytest.raises(ValueError, match="expected a JSON object"):
        localization._load_user_preferences()


def test_user_preferences_reject_unsupported_language() -> None:
    with pytest.raises(ValueError, match="unsupported language code"):
        localization._load_preferences_from_json('{"123": "fr"}', Path("prefs.json"))


def test_user_preferences_reject_non_string_user_id() -> None:
    with pytest.raises(TypeError, match="invalid user id key"):
        localization._validate_language_preferences(Path("prefs.json"), {123: "en"})


def test_translation_file_rejects_non_string_values() -> None:
    with pytest.raises(TypeError, match="non-string translation"):
        localization._validate_translations(Path("en.json"), {"hello": 123})


def test_load_language_rejects_unsupported_language() -> None:
    with pytest.raises(ValueError, match="Unsupported language code"):
        localization.load_language("fr")


def test_initialize_localization_uses_configured_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    locales_dir = tmp_path / "locales"
    prefs_path = tmp_path / "user_lang_prefs.json"
    locales_dir.mkdir()
    (locales_dir / "en.json").write_text(json.dumps({"hello": "Hello"}), encoding="utf-8")
    (locales_dir / "zh_TW.json").write_text(json.dumps({"hello": "哈囉"}), encoding="utf-8")
    prefs_path.write_text(json.dumps({"123": "zh_TW"}), encoding="utf-8")
    monkeypatch.setattr(localization, "LOCALES_DIR", locales_dir)
    monkeypatch.setattr(localization, "USER_PREFS_FILE", prefs_path)

    localization.initialize_localization()

    assert localization.get_user_language("123") == "zh_TW"
    assert localization.get_localized_string("123", "hello") == "哈囉"


def test_user_bindings_reject_empty_json_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(user_data_manager, "DATA_FILE", bindings_path)

    with pytest.raises(ValueError, match="expected a JSON object"):
        asyncio.run(user_data_manager.load_user_bindings())


def test_user_bindings_reject_non_object_json() -> None:
    with pytest.raises(TypeError, match="must contain a JSON object"):
        user_data_manager._load_bindings_from_json('["123"]', Path("bindings.json"))


def test_user_bindings_reject_non_string_discord_id() -> None:
    with pytest.raises(TypeError, match="invalid Discord user id key"):
        user_data_manager._validate_user_bindings(Path("bindings.json"), {123: "osu_user"})


def test_user_bindings_reject_empty_osu_user() -> None:
    with pytest.raises(TypeError, match="invalid osu! binding"):
        user_data_manager._validate_user_bindings(Path("bindings.json"), {"123": ""})


def test_missing_user_bindings_file_returns_empty_bindings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(user_data_manager, "DATA_FILE", tmp_path / "missing.json")

    assert asyncio.run(user_data_manager.load_user_bindings()) == {}


def test_user_bindings_round_trip_uses_configured_data_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(user_data_manager, "DATA_FILE", tmp_path / "bindings.json")

    asyncio.run(_assert_user_binding_round_trip())


async def _assert_user_binding_round_trip() -> None:
    assert await user_data_manager.set_user_binding(123, "peppy")
    assert await user_data_manager.get_user_binding(123) == "peppy"
    assert await user_data_manager.remove_user_binding(123)
    assert await user_data_manager.get_user_binding(123) is None
