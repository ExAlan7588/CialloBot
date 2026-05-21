from __future__ import annotations

import sys
import types

import pytest

DEFAULT_TEST_CONFIG: dict[str, object] = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "OSU_API_V2_CLIENT_ID": "dummy-client-id",
    "OSU_API_V2_CLIENT_SECRET": "dummy-client-secret",
    "OSU_API_V1_KEY": "dummy-api-v1-key",
    "DEFAULT_LANGUAGE": "en",
    "SUPPORTED_LANGUAGES": {"en": "English", "zh_TW": "Traditional Chinese"},
}

test_config = types.ModuleType("private.config")
sys.modules["private.config"] = test_config


def _apply_test_config() -> None:
    for name, value in DEFAULT_TEST_CONFIG.items():
        setattr(test_config, name, value)


_apply_test_config()


@pytest.fixture(autouse=True)
def reset_private_config() -> None:
    _apply_test_config()
