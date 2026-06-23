"""Thread management API (LangGraph-compatible)."""

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
    """Create a new conversation thread.

    Returns the thread_id; the actual checkpoint is created on the first run.
    """
    thread_id = body.thread_id or str(uuid.uuid4())
    return ThreadResponse(thread_id=thread_id, metadata=body.metadata)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(thread_id: str, request: Request) -> ThreadResponse:
    """Get thread metadata."""
    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await checkpointer.aget_tuple(config)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return ThreadResponse(thread_id=thread_id, metadata={})
