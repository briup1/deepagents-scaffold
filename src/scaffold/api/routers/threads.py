"""线程管理 API（兼容 LangGraph）。"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from langgraph.checkpoint.base import Checkpoint
from pydantic import BaseModel, Field

from scaffold.api.deps import get_checkpointer, get_history_repo
from scaffold.infra.history import ThreadMessage, ThreadSummary

router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadCreateRequest(BaseModel):
    thread_id: str | None = Field(default=None, description="Optional explicit thread ID")
    agent_id: str = Field(default="default", description="绑定 Agent 名称")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadResponse(BaseModel):
    thread_id: str
    metadata: dict[str, Any]


class ThreadsListResponse(BaseModel):
    threads: list[ThreadSummary]
    total: int


class ThreadMessagesResponse(BaseModel):
    thread_id: str
    messages: list[ThreadMessage]


@router.post("/", response_model=ThreadResponse)
async def create_thread(body: ThreadCreateRequest, request: Request) -> ThreadResponse:
    """创建新的会话线程。

    创建时即写入一个空的初始 checkpoint，以便创建后可立即通过
    ``GET /api/threads/{thread_id}`` 和 ``GET /api/threads/{thread_id}/state``
    查询线程元数据及状态。
    """
    thread_id = body.thread_id or str(uuid.uuid4())
    checkpointer = get_checkpointer(request)
    history_repo = get_history_repo(request)

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = Checkpoint(
        v=1,
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        channel_values={},
        channel_versions={},
        versions_seen={},
        updated_channels=set(),
    )
    checkpoint_metadata = {"source": "thread_create", "step": -1, **body.metadata}
    await checkpointer.aput(
        config,
        checkpoint=checkpoint,
        metadata=checkpoint_metadata,
        new_versions={},
    )

    # 同步写入历史线程表
    await history_repo.ensure_thread(thread_id, body.agent_id)

    return ThreadResponse(thread_id=thread_id, metadata=checkpoint_metadata)


@router.get("/", response_model=ThreadsListResponse)
async def list_threads(
    request: Request,
    agent_id: str | None = Query(default=None, description="按 Agent 过滤"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ThreadsListResponse:
    """列出历史会话。"""
    history_repo = get_history_repo(request)
    threads, total = await history_repo.list_threads(agent_id=agent_id, limit=limit, offset=offset)
    return ThreadsListResponse(threads=threads, total=total)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str, request: Request) -> ThreadResponse:
    """获取线程元数据。"""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    thread_metadata = checkpoint.metadata if hasattr(checkpoint, "metadata") and checkpoint.metadata else {}
    return ThreadResponse(thread_id=thread_id, metadata=thread_metadata)


@router.get("/{thread_id}/messages", response_model=ThreadMessagesResponse)
async def get_thread_messages(thread_id: str, request: Request) -> ThreadMessagesResponse:
    """获取某会话的全部消息。"""
    history_repo = get_history_repo(request)
    messages = await history_repo.get_messages(thread_id)
    return ThreadMessagesResponse(thread_id=thread_id, messages=messages)
