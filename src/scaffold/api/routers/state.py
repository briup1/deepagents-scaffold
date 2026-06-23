"""Thread state API.

Get and update LangGraph thread state.
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
    """Get the current state of a thread."""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # checkpoint is a CheckpointTuple with .checkpoint dict
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
    """Update thread state (merge with existing)."""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # Store updated state
    await checkpointer.aput(
        config,
        checkpoint=body.state,
        metadata={"source": "api_update"},
        new_versions={},
    )

    return ThreadStateResponse(thread_id=thread_id, state=body.state)
