"""Middleware configuration schema.

定义 middleware 在 config.yaml 中的声明方式及其在运行时的实例化逻辑。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MiddlewareConfig(BaseModel):
    """单个 middleware 实例的配置。"""

    name: str = Field(..., description="Middleware class name or registered alias")
    enabled: bool = Field(default=True, description="Whether this middleware is active")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Constructor kwargs")


class MiddlewareChainConfig(BaseModel):
    """注入 DeepAgents 的有序 middleware 链配置。"""

    items: list[MiddlewareConfig] = Field(default_factory=list)

    def get_enabled(self) -> list[MiddlewareConfig]:
        """仅返回按声明顺序排列的已启用 middleware 配置。"""
        return [m for m in self.items if m.enabled]
