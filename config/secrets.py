from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def _load_private_config() -> Any | None:
    try:
        from private import config as private_config
    except ImportError:
        return None
    return private_config


_PRIVATE_CONFIG = _load_private_config()


def _get_value(name: str, default: str | None = None) -> str | None:
    env_value = os.getenv(name)
    if env_value is not None and env_value != "":
        return env_value

    if _PRIVATE_CONFIG is not None and hasattr(_PRIVATE_CONFIG, name):
        private_value = getattr(_PRIVATE_CONFIG, name)
        if private_value is not None and private_value != "":
            return str(private_value)

    return default


def _get_int(name: str, default: int) -> int:
    value = _get_value(name)
    if value is None:
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = _get_value(name)
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True, slots=True)
class Secrets:
    DATABASE_URL: str | None
    PG_HOST: str | None
    PG_PORT: int
    PG_USER: str | None
    PG_PASSWORD: str | None
    PG_DATABASE: str | None
    PG_POOL_MIN_SIZE: int
    PG_POOL_MAX_SIZE: int
    PG_CONNECT_TIMEOUT_SECONDS: float


def load_secrets() -> Secrets:
    return Secrets(
        DATABASE_URL=_get_value("DATABASE_URL"),
        PG_HOST=_get_value("PG_HOST"),
        PG_PORT=_get_int("PG_PORT", 5432),
        PG_USER=_get_value("PG_USER"),
        PG_PASSWORD=_get_value("PG_PASSWORD"),
        PG_DATABASE=_get_value("PG_DATABASE"),
        PG_POOL_MIN_SIZE=_get_int("PG_POOL_MIN_SIZE", 1),
        PG_POOL_MAX_SIZE=_get_int("PG_POOL_MAX_SIZE", 10),
        PG_CONNECT_TIMEOUT_SECONDS=_get_float("PG_CONNECT_TIMEOUT_SECONDS", 10.0),
    )
