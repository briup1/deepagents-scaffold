"""子 Agent 配置 schema。

定义可在 config.yaml 中声明并传给 create_deep_agent(subagents=[...]) 的子 Agent 规格。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PermissionRuleConfig(BaseModel):
    """单条文件系统权限规则配置。"""

    paths: list[str] = Field(..., description="Path patterns (must start with '/')")
    operations: list[Literal["read", "write"]] = Field(..., description="Allowed operations")
    mode: Literal["allow", "deny", "interrupt"] = Field(default="allow", description="Effect when rule matches")

    @model_validator(mode="after")
    def validate_paths(self) -> "PermissionRuleConfig":
        for path in self.paths:
            if not path.startswith("/"):
                raise ValueError(f"Permission path must start with '/': {path!r}")
            parts = path.replace("\\", "/").split("/")
            if ".." in parts:
                raise ValueError(f"Permission path must not contain '..': {path!r}")
            if "~" in parts:
                raise ValueError(f"Permission path must not contain '~': {path!r}")
        return self


class SubAgentDefinitionConfig(BaseModel):
    """单个 subagent 定义的配置。"""

    name: str = Field(..., description="Unique identifier for the subagent")
    description: str = Field(..., description="What this subagent does")
    system_prompt: str = Field(..., description="Instructions for the subagent")
    model: str | None = Field(default=None, description="Override model (provider:model-name)")
    tools: list[str] = Field(default_factory=list, description="Tool names this subagent can use")
    skills: list[str] = Field(default_factory=list, description="Skill paths")
    middleware: list[str] = Field(default_factory=list, description="Middleware class names")
    permissions: list[PermissionRuleConfig] = Field(default_factory=list, description="Filesystem permission rules")
    interrupt_on: dict[str, Any] = Field(default_factory=dict, description="HIL configuration")
    enabled: bool = Field(default=True, description="Whether this subagent is active")


class SubAgentsDefinitionsConfig(BaseModel):
    """subagent 定义集合。"""

    items: list[SubAgentDefinitionConfig] = Field(default_factory=list)

    def get_enabled(self) -> list[SubAgentDefinitionConfig]:
        """仅返回启用的 subagent 定义。"""
        return [s for s in self.items if s.enabled]
