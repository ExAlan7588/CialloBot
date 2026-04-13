from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from config.secrets import Secrets, load_secrets


@dataclass(frozen=True, slots=True)
class CoreSettings:
    database_url: str | None


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    pool_min_size: int
    pool_max_size: int
    connect_timeout_seconds: float


@dataclass(frozen=True, slots=True)
class AppSettings:
    core: CoreSettings
    database: DatabaseSettings


def _build_database_url(secrets: Secrets) -> str | None:
    if secrets.DATABASE_URL:
        return secrets.DATABASE_URL

    if not all(
        [
            secrets.PG_HOST,
            secrets.PG_USER,
            secrets.PG_PASSWORD,
            secrets.PG_DATABASE,
        ]
    ):
        return None

    user = quote_plus(secrets.PG_USER or "")
    password = quote_plus(secrets.PG_PASSWORD or "")
    database_name = quote(secrets.PG_DATABASE or "", safe="")

    return (
        f"postgresql://{user}:{password}"
        f"@{secrets.PG_HOST}:{secrets.PG_PORT}/{database_name}"
    )


def load_settings() -> AppSettings:
    secrets = load_secrets()

    return AppSettings(
        core=CoreSettings(database_url=_build_database_url(secrets)),
        database=DatabaseSettings(
            pool_min_size=secrets.PG_POOL_MIN_SIZE,
            pool_max_size=secrets.PG_POOL_MAX_SIZE,
            connect_timeout_seconds=secrets.PG_CONNECT_TIMEOUT_SECONDS,
        ),
    )


settings = load_settings()
