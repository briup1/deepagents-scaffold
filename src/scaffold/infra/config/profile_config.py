"""Profile configuration schema.

HarnessProfile 与 ProviderProfile 的 DeepAgents 自定义配置。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HarnessProfileConfig(BaseModel):
    """HarnessProfile 的配置。"""

    name: str = Field(..., description="Profile identifier")
    base_system_prompt: str | None = Field(default=None, description="Replaces BASE prompt segment")
    system_prompt_suffix: str | None = Field(default=None, description="Appended after BASE")
    excluded_middleware: list[str] = Field(default_factory=list, description="Middleware names to exclude")
    excluded_tools: list[str] = Field(default_factory=list, description="Tool names to exclude")
    # 三态：None=继承全局 skills.path；[]=明确不挂 skill；[路径]=域目录白名单
    skills: list[str] | None = Field(default=None, description="Skill source dirs; None inherits global pool")
    extra_tools: list[dict[str, Any]] = Field(default_factory=list, description="Additional tool definitions")


class ProviderProfileConfig(BaseModel):
    """ProviderProfile 的配置。"""

    name: str = Field(..., description="Provider identifier")
    model_pattern: str | None = Field(default=None, description="Model name regex pattern")
    system_prompt: str | None = Field(default=None, description="Provider-specific system prompt")


class ProfilesConfig(BaseModel):
    """根 profile 配置。"""

    harness: list[HarnessProfileConfig] = Field(default_factory=list)
    providers: list[ProviderProfileConfig] = Field(default_factory=list)
    default_harness: str | None = Field(default=None, description="Default harness profile name")
