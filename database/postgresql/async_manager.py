from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg
from loguru import logger

from config.settings import load_settings
from utils.misc import capture_exception


class _DatabaseManager:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def _init_db_connection(self, conn: asyncpg.Connection) -> None:
        def json_dumps(value: Any) -> str:
            return json.dumps(value, ensure_ascii=False, default=str)

        try:
            await conn.set_type_codec(
                "json",
                encoder=json_dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )
            await conn.set_type_codec(
                "jsonb",
                encoder=json_dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )
        except Exception as exc:
            capture_exception(
                exc,
                context="初始化 PostgreSQL JSON codec 失敗",
                level="warning",
            )

    async def setup_connections(self) -> bool:
        if self.pool and not self.pool.is_closing():
            logger.info("PostgreSQL 連線池已存在，跳過重複初始化")
            return True

        current_settings = load_settings()
        db_url = current_settings.core.database_url
        if not db_url:
            logger.warning("未配置 PostgreSQL 連線資訊，跳過資料庫初始化")
            return False

        try:
            self.pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=current_settings.database.pool_min_size,
                max_size=current_settings.database.pool_max_size,
                timeout=current_settings.database.connect_timeout_seconds,
                init=self._init_db_connection,
            )
        except Exception as exc:
            capture_exception(exc, context="初始化 PostgreSQL 連線池失敗")
            msg = f"無法初始化 PostgreSQL 連線池: {exc}"
            raise RuntimeError(msg) from exc

        logger.info("PostgreSQL 連線池初始化成功")
        return True

    async def close_connections(self) -> None:
        if self.pool is None:
            return

        try:
            await self.pool.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            capture_exception(exc, context="關閉 PostgreSQL 連線池失敗", level="warning")
        finally:
            self.pool = None


_db_manager = _DatabaseManager()


async def setup_connections() -> bool:
    return await _db_manager.setup_connections()


async def close_connections() -> None:
    await _db_manager.close_connections()


def get_pool() -> asyncpg.Pool:
    if _db_manager.pool is None:
        msg = "PostgreSQL 連線池尚未初始化。"
        raise RuntimeError(msg)
    return _db_manager.pool
