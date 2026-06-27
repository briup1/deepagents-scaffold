"""模型工厂 — 根据配置创建 LLM 实例。

从 deerflow.models.factory 移植并简化，适配本脚手架。
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from scaffold.infra.config.model_config import ModelConfig

logger = logging.getLogger(__name__)


def _resolve_env_variables(value: Any) -> Any:
    """递归解析 $ENV_VAR 占位符。"""
    if isinstance(value, str) and value.startswith("$"):
        env_name = value[1:]
        env_value = os.getenv(env_name)
        if env_value is None:
            raise ValueError(f"Environment variable {env_name} not found for config value {value}")
        return env_value
    if isinstance(value, dict):
        return {k: _resolve_env_variables(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_variables(item) for item in value]
    return value


def _import_class(class_path: str) -> type:
    """从 'module.path:ClassName' 导入类。"""
    module_path, class_name = class_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _maybe_patch_deepseek(cls: type, config: ModelConfig) -> type:
    """使用原生 DeepSeek adapter 时应用 Deer-Flow 的 PatchedChatDeepSeek。

    DeepSeek 的 reasoning/thinking 模式要求多轮对话中所有 assistant 消息
    都包含 reasoning_content。原生的 ChatDeepSeek 将其存储在 additional_kwargs 中，
    但在后续 API 调用时会丢失。PatchedChatDeepSeek 会在多轮对话中保留该字段。

    参见: deerflow/models/patched_deepseek.py
    """
    if config.use == "langchain_deepseek:ChatDeepSeek":
        try:
            from langchain_deepseek import ChatDeepSeek

            if issubclass(cls, ChatDeepSeek):
                logger.debug("Applying PatchedChatDeepSeek for %s", config.name)
                return _import_class("scaffold.infra.models.patched_deepseek:PatchedChatDeepSeek")
        except Exception:
            logger.warning("Failed to apply PatchedChatDeepSeek, falling back to %s", config.use)
    return cls


def create_chat_model(
    config: ModelConfig,
    *,
    thinking_enabled: bool = False,
    **overrides: Any,
) -> BaseChatModel:
    """根据 ModelConfig 实例化一个聊天模型。

    Args:
        config: 模型配置。
        thinking_enabled: 是否启用模型 thinking/reasoning。
        **overrides: 额外传入模型构造器的参数。

    Returns:
        已实例化的 LangChain 聊天模型。
    """
    raw_cls = _import_class(config.use)
    cls = _maybe_patch_deepseek(raw_cls, config)

    # 从配置构建 kwargs
    kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
    }
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    if config.api_key is not None:
        kwargs["api_key"] = _resolve_env_variables(config.api_key)
    if config.base_url is not None:
        kwargs["base_url"] = _resolve_env_variables(config.base_url)
    if config.api_version is not None:
        kwargs["api_version"] = _resolve_env_variables(config.api_version)

    # 合并 provider 特定的额外参数（上面未显式处理的任何字段）
    extras = {
        k: v
        for k, v in config.model_dump().items()
        if k
        not in {
            "name",
            "display_name",
            "use",
            "api_key",
            "model",
            "temperature",
            "max_tokens",
            "base_url",
            "api_version",
            "supports_thinking",
            "supports_vision",
            "when_thinking_enabled",
        }
        and v is not None
    }
    kwargs.update(extras)

    # 应用 thinking 覆盖参数
    if thinking_enabled and config.when_thinking_enabled:
        for key, value in config.when_thinking_enabled.items():
            if key in kwargs and isinstance(kwargs[key], dict) and isinstance(value, dict):
                kwargs[key] = {**kwargs[key], **value}
            else:
                kwargs[key] = value

    # 应用调用方覆盖参数
    kwargs.update(overrides)

    # 解析嵌套值中剩余的 $ENV_VAR
    kwargs = _resolve_env_variables(kwargs)

    logger.debug("Creating chat model %s with kwargs %s", config.name, list(kwargs.keys()))
    return cls(**kwargs)
