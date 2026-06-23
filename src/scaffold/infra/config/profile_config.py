"""Profile configuration schema.

HarnessProfile and ProviderProfile settings for DeepAgents customization.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HarnessProfileConfig(BaseModel):
    """Configuration for a HarnessProfile."""

    name: str = Field(..., description="Profile identifier")
    base_system_prompt: str | None = Field(default=None, description="Replaces BASE prompt segment")
    system_prompt_suffix: str | None = Field(default=None, description="Appended after BASE")
    excluded_middleware: list[str] = Field(default_factory=list, description="Middleware names to exclude")
    excluded_tools: list[str] = Field(default_factory=list, description="Tool names to exclude")
    extra_tools: list[dict[str, Any]] = Field(default_factory=list, description="Additional tool definitions")


class ProviderProfileConfig(BaseModel):
    """Configuration for a ProviderProfile."""

    name: str = Field(..., description="Provider identifier")
    model_pattern: str | None = Field(default=None, description="Model name regex pattern")
    system_prompt: str | None = Field(default=None, description="Provider-specific system prompt")


class ProfilesConfig(BaseModel):
    """Root profile configuration."""

    harness: list[HarnessProfileConfig] = Field(default_factory=list)
    providers: list[ProviderProfileConfig] = Field(default_factory=list)
    default_harness: str | None = Field(default=None, description="Default harness profile name")
