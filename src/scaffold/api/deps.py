"""Dependency injection for FastAPI routes.

Provides singleton accessors and lifespan management for LangGraph runtime.
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
from scaffold.runtime.stream_bridge.async_provider import make_stream_bridge

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)


def get_config() -> AppConfig:
    """Return the freshest AppConfig for the current request."""
    try:
        return get_app_config()
    except Exception as exc:
        logger.exception("Failed to load AppConfig")
        raise HTTPException(status_code=503, detail="Configuration not available") from exc


@asynccontextmanager
async def scaffold_runtime(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bootstrap LangGraph runtime: checkpointer, store, etc.

    Stores singletons on app.state for request-time access.
    """
    config = get_config()

    async with AsyncExitStack() as stack:
        # SQLite checkpointer (default)
        db_path = f"{config.database.sqlite_dir}/checkpoints.db"
        os.makedirs(config.database.sqlite_dir, exist_ok=True)

        conn = await aiosqlite.connect(db_path)
        stack.push_async_callback(conn.close)
        checkpointer = AsyncSqliteSaver(conn)
        app.state.checkpointer = checkpointer
        logger.info("Checkpointer initialized at %s", db_path)

        bridge = await stack.enter_async_context(make_stream_bridge(config.stream_bridge.model_dump()))
        app.state.stream_bridge = bridge
        logger.info("Stream bridge initialized (type=%s)", config.stream_bridge.type)

        yield

        # Cleanup
        logger.info("Shutting down scaffold runtime")


def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        raise HTTPException(status_code=503, detail="Checkpointer not initialized")
    return cp


def get_stream_bridge(request: Request):
    bridge = getattr(request.app.state, "stream_bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="Stream bridge not initialized")
    return bridge
