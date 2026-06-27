"""线程管理 API（兼容 LangGraph）。"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from scaffold.api.deps import get_checkpointer, get_config

router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadCreateRequest(BaseModel):
    thread_id: str | None = Field(default=None, description="Optional explicit thread ID")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadResponse(BaseModel):
    thread_id: str
    metadata: dict[str, Any]


@router.post("/", response_model=ThreadResponse)
async def create_thread(body: ThreadCreateRequest, request: Request) -> ThreadResponse:
    """创建新的会话线程。

    返回 thread_id；实际的 checkpoint 在首次运行时创建。
    """
    thread_id = body.thread_id or str(uuid.uuid4())
    return ThreadResponse(thread_id=thread_id, metadata=body.metadata)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str, request: Request) -> ThreadResponse:
    """获取线程元数据。"""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return ThreadResponse(thread_id=thread_id, metadata={})
