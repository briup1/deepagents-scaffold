"""历史消息数据模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    """创建线程请求。"""

    thread_id: str | None = Field(default=None, description="可选显式线程 ID")
    agent_id: str = Field(default="default", description="绑定 Agent 名称")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadSummary(BaseModel):
    """线程列表项。"""

    thread_id: str
    agent_id: str
    title: str | None
    last_message_preview: str | None
    created_at: str
    updated_at: str


class ThreadMessage(BaseModel):
    """单条历史消息。"""

    message_id: str
    run_id: str | None
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    created_at: str
