"""工具配置 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    """自定义工具的配置。"""

    name: str = Field(..., description="Tool name exposed to the agent")
    use: str = Field(..., description="Import path, e.g. mymodule:my_async_function")
    description: str | None = Field(default=None, description="Override the function docstring")
    group: str | None = Field(default=None, description="Tool group for selective enabling")


class ToolGroupConfig(BaseModel):
    """工具组的配置。"""

    name: str = Field(..., description="Group identifier")
    description: str = Field(default="", description="Group description")
