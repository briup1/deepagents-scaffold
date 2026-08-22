"""工件数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    """代表一次上传或生成的会话工件。"""

    artifact_id: str
    thread_id: str
    artifact_type: Literal["upload", "script", "extraction", "report"]
    original_name: str | None = None
    stored_path: str
    mime_type: str | None = None
    size_bytes: int = 0
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
