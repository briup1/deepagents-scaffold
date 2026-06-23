"""Backend configuration schema.

Mirrors deer-flow's backend configuration for DeepAgents integration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FilesystemBackendConfig(BaseModel):
    """Configuration for FilesystemBackend."""

    root_dir: str = Field(default="/", description="Root directory for file operations")


class SandboxBackendConfig(BaseModel):
    """Configuration for sandbox execution backend."""

    provider: str = Field(default="local", description="Sandbox provider: local, docker, e2b")
    timeout_seconds: int = Field(default=60, description="Command timeout")
    mounts: list[dict[str, str]] = Field(default_factory=list, description="Volume mounts")


class BackendConfig(BaseModel):
    """Root backend configuration."""

    type: str = Field(default="filesystem", description="Backend type: filesystem, sandbox, composite")
    filesystem: FilesystemBackendConfig = Field(default_factory=FilesystemBackendConfig)
    sandbox: SandboxBackendConfig = Field(default_factory=SandboxBackendConfig)
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Extra backend kwargs")
