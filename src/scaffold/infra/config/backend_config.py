"""Backend 配置 schema。

映射 deer-flow 的 backend 配置，用于 DeepAgents 集成。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FilesystemBackendConfig(BaseModel):
    """FilesystemBackend 的配置。"""

    root_dir: str = Field(default="/", description="Root directory for file operations")


class SandboxBackendConfig(BaseModel):
    """沙箱执行 backend 的配置。"""

    provider: str = Field(default="local", description="Sandbox provider: local, docker, e2b")
    timeout_seconds: int = Field(default=60, description="Command timeout")
    mounts: list[dict[str, str]] = Field(default_factory=list, description="Volume mounts")


class BackendConfig(BaseModel):
    """根 backend 配置。"""

    type: str = Field(default="filesystem", description="Backend type: filesystem, sandbox, composite")
    filesystem: FilesystemBackendConfig = Field(default_factory=FilesystemBackendConfig)
    sandbox: SandboxBackendConfig = Field(default_factory=SandboxBackendConfig)
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Extra backend kwargs")
