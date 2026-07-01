"""模型配置 schema 与辅助工具。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """单个 LLM provider 的配置。"""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Unique identifier for this model config")
    display_name: str = Field(..., description="Human-readable model name")
    use: str = Field(..., description="Import path, e.g. langchain_openai:ChatOpenAI")
    api_key: str | None = Field(default=None, description="API key (supports $ENV_VAR)")
    model: str = Field(..., description="Model identifier passed to the provider")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    base_url: str | None = Field(
        default=None, description="Custom API base URL (e.g. for DeepSeek via OpenAI-compatible endpoint)"
    )
    api_version: str | None = Field(default=None, description="API version for Azure/OpenAI-compatible endpoints")
    supports_thinking: bool = Field(default=False)
    supports_vision: bool = Field(default=False)
    # 启用 thinking 时的 provider 专属覆盖参数
    when_thinking_enabled: dict[str, Any] | None = Field(default=None)
    bypass_proxy: bool = Field(
        default=False,
        description="If True, model calls bypass HTTP(S)_PROXY env vars by using proxy-free httpx clients",
    )
