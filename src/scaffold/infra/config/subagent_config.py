"""SubAgent configuration schema.

Defines subagent specifications that can be declared in config.yaml
and passed to create_deep_agent(subagents=[...]).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubAgentDefinitionConfig(BaseModel):
    """Configuration for a single subagent definition."""

    name: str = Field(..., description="Unique identifier for the subagent")
    description: str = Field(..., description="What this subagent does")
    system_prompt: str = Field(..., description="Instructions for the subagent")
    model: str | None = Field(default=None, description="Override model (provider:model-name)")
    tools: list[str] = Field(default_factory=list, description="Tool names this subagent can use")
    skills: list[str] = Field(default_factory=list, description="Skill paths")
    middleware: list[str] = Field(default_factory=list, description="Middleware class names")
    permissions: list[str] = Field(default_factory=list, description="Filesystem permissions")
    interrupt_on: dict[str, Any] = Field(default_factory=dict, description="HIL configuration")
    enabled: bool = Field(default=True, description="Whether this subagent is active")


class SubAgentsDefinitionsConfig(BaseModel):
    """Collection of subagent definitions."""

    items: list[SubAgentDefinitionConfig] = Field(default_factory=list)

    def get_enabled(self) -> list[SubAgentDefinitionConfig]:
        """Return only enabled subagent definitions."""
        return [s for s in self.items if s.enabled]
