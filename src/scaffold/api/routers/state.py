"""线程状态 API。

获取和更新 LangGraph 线程状态。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from scaffold.api.deps import get_checkpointer

router = APIRouter(prefix="/api/threads", tags=["state"])


class ThreadStateResponse(BaseModel):
    thread_id: str
    state: dict[str, Any]


class ThreadStateUpdateRequest(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)


@router.get("/{thread_id}/state", response_model=ThreadStateResponse)
async def get_thread_state(thread_id: str, request: Request) -> ThreadStateResponse:
    """获取线程的当前状态。"""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # checkpoint 是一个 CheckpointTuple，包含 .checkpoint 字典
    state = checkpoint.checkpoint if hasattr(checkpoint, "checkpoint") else {}
    if isinstance(state, dict) and "channel_values" in state:
        state = state["channel_values"]

    return ThreadStateResponse(thread_id=thread_id, state=state or {})


@router.post("/{thread_id}/state", response_model=ThreadStateResponse)
async def update_thread_state(
    thread_id: str,
    body: ThreadStateUpdateRequest,
    request: Request,
) -> ThreadStateResponse:
    """更新线程状态（与现有状态合并）。"""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # 存储更新后的状态
    await checkpointer.aput(
        config,
        checkpoint=body.state,
        metadata={"source": "api_update"},
        new_versions={},
    )

    return ThreadStateResponse(thread_id=thread_id, state=body.state)
