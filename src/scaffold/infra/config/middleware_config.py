"""Middleware configuration schema.

Defines how middleware is declared in config.yaml and instantiated at runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MiddlewareConfig(BaseModel):
    """Configuration for a single middleware instance."""

    name: str = Field(..., description="Middleware class name or registered alias")
    enabled: bool = Field(default=True, description="Whether this middleware is active")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Constructor kwargs")


class MiddlewareChainConfig(BaseModel):
    """Configuration for the ordered middleware chain injected into DeepAgents."""

    items: list[MiddlewareConfig] = Field(default_factory=list)

    def get_enabled(self) -> list[MiddlewareConfig]:
        """Return only enabled middleware configs in declared order."""
        return [m for m in self.items if m.enabled]
