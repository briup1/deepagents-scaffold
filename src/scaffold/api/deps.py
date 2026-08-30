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
from scaffold.infra.artifacts import ArtifactRepository
from scaffold.infra.history import HistoryRepository

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


def get_request_user_id(request: Request) -> str:
    """从 request.state 读取 AuthMiddleware 写入的 user_id（缺失时为 'default'）。"""
    return getattr(request.state, "user_id", None) or "default"


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

        # 历史消息库
        history_db_path = config.database.history_db or f"{config.database.sqlite_dir}/history.db"
        os.makedirs(os.path.dirname(history_db_path), exist_ok=True)
        history_conn = await aiosqlite.connect(history_db_path)
        stack.push_async_callback(history_conn.close)
        history_repo = HistoryRepository(history_conn)
        await history_repo.migrate()

        # 工件元数据仓库（复用历史库连接）
        artifact_repo = ArtifactRepository(history_conn)
        await artifact_repo.migrate()
        app.state.artifact_repo = artifact_repo

        app.state.history_repo = history_repo
        logger.info("History repository initialized at %s", history_db_path)

        yield

        # 清理
        logger.info("Shutting down scaffold runtime")


def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        raise HTTPException(status_code=503, detail="Checkpointer not initialized")
    return cp


def get_history_repo(request: Request) -> HistoryRepository:
    """返回当前请求的历史仓库实例。"""
    repo = getattr(request.app.state, "history_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="History repository not initialized")
    return repo


def get_artifact_repo(request: Request) -> ArtifactRepository:
    """返回当前请求的工件仓库实例。"""
    repo = getattr(request.app.state, "artifact_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Artifact repository not initialized")
    return repo
