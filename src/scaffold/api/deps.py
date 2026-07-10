"""FastAPI 路由的依赖注入。

为 LangGraph 运行时提供单例访问器和生命周期管理。
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import aiosqlite
from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from scaffold.infra.config.app_config import AppConfig, get_app_config

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)


def get_config() -> AppConfig:
    """返回当前请求最新的 AppConfig。"""
    try:
        return get_app_config()
    except Exception as exc:
        logger.exception("Failed to load AppConfig")
        raise HTTPException(status_code=503, detail="Configuration not available") from exc


@asynccontextmanager
async def scaffold_runtime(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动 LangGraph 运行时：checkpointer、store 等。

    将单例存储在 app.state 中，供请求时访问。
    """
    config = get_config()

    async with AsyncExitStack() as stack:
        # SQLite checkpointer（默认）
        db_path = f"{config.database.sqlite_dir}/checkpoints.db"
        os.makedirs(config.database.sqlite_dir, exist_ok=True)

        conn = await aiosqlite.connect(db_path)
        stack.push_async_callback(conn.close)
        checkpointer = AsyncSqliteSaver(conn)
        app.state.checkpointer = checkpointer
        logger.info("Checkpointer initialized at %s", db_path)

        yield

        # 清理
        logger.info("Shutting down scaffold runtime")


def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        raise HTTPException(status_code=503, detail="Checkpointer not initialized")
    return cp
