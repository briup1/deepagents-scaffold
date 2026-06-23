"""Model factory — create LLM instances from config.

Adapted from deerflow.models.factory, simplified for the scaffold.
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
    """Recursively resolve $ENV_VAR placeholders."""
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
    """Import a class from 'module.path:ClassName'."""
    module_path, class_name = class_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _maybe_patch_deepseek(cls: type, config: ModelConfig) -> type:
    """Apply Deer-Flow's PatchedChatDeepSeek when using native DeepSeek adapter.

    DeepSeek's reasoning/thinking mode requires reasoning_content to be present
    on ALL assistant messages in multi-turn conversations. The original
    ChatDeepSeek stores it in additional_kwargs but drops it on subsequent API
    calls. PatchedChatDeepSeek preserves it across turns.

    See: deerflow/models/patched_deepseek.py
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
    """Instantiate a chat model from a ModelConfig.

    Args:
        config: The model configuration.
        thinking_enabled: Whether to enable model thinking/reasoning.
        **overrides: Additional kwargs passed to the model constructor.

    Returns:
        An instantiated LangChain chat model.
    """
    raw_cls = _import_class(config.use)
    cls = _maybe_patch_deepseek(raw_cls, config)

    # Build kwargs from config
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

    # Merge provider-specific extras (anything not explicitly handled above)
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

    # Apply thinking overrides
    if thinking_enabled and config.when_thinking_enabled:
        for key, value in config.when_thinking_enabled.items():
            if key in kwargs and isinstance(kwargs[key], dict) and isinstance(value, dict):
                kwargs[key] = {**kwargs[key], **value}
            else:
                kwargs[key] = value

    # Apply caller overrides
    kwargs.update(overrides)

    # Resolve any remaining $ENV_VAR in nested values
    kwargs = _resolve_env_variables(kwargs)

    logger.debug("Creating chat model %s with kwargs %s", config.name, list(kwargs.keys()))
    return cls(**kwargs)
