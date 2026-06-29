"""Middleware factory.

从 MiddlewareConfig 声明构建 AgentMiddleware 实例。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.config.middleware_config import MiddlewareChainConfig
from scaffold.infra.middleware.deerflow_adapters.tool_error_handling import ToolErrorHandlingMiddleware
from scaffold.infra.middleware.registry import get_middleware_registry

logger = logging.getLogger(__name__)


def _resolve_kwargs(kwargs: dict[str, Any], app_config: AppConfig) -> dict[str, Any]:
    """解析 middleware kwargs 中的配置引用。

    支持：
    - $config.memory — 注入 MemoryConfig dict
    - $config.models[0] — 注入第一个 ModelConfig dict
    - $env.VAR_NAME — 环境变量
    """
    resolved: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and value.startswith("$"):
            ref = value[1:]
            if ref.startswith("config."):
                attr_path = ref[7:]  # e.g. 'memory' or 'models[0]'
                resolved[key] = _get_config_attr(app_config, attr_path)
            elif ref.startswith("env."):
                env_name = ref[4:]
                import os

                env_value = os.getenv(env_name)
                if env_value is None:
                    raise ValueError(f"Environment variable {env_name} not found for middleware kwarg")
                resolved[key] = env_value
            else:
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


def _get_config_attr(app_config: AppConfig, attr_path: str) -> Any:
    """解析点号分隔的配置属性路径。"""
    parts = attr_path.split(".")
    obj: Any = app_config
    for part in parts:
        if hasattr(obj, part):
            obj = getattr(obj, part)
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            raise ValueError(f"Config attribute '{attr_path}' not found (failed at '{part}')")
    return obj


def build_middleware_chain(
    config: MiddlewareChainConfig | None = None,
    app_config: AppConfig | None = None,
) -> list[AgentMiddleware[Any, Any, Any]]:
    """从 config 构建有序的 AgentMiddleware 实例列表。

    Args:
        config: middleware 链配置。省略时从 app_config 加载。
        app_config: 用于解析 $config 引用的 AppConfig。

    Returns:
        供 create_deep_agent(middleware=...) 使用的有序 middleware 实例列表。
    """
    if app_config is None:
        app_config = get_app_config()

    if config is None:
        # 尝试从 app_config 获取；回退到空链
        chain_cfg = getattr(app_config, "middleware", None)
        if chain_cfg is None:
            return []
        config = chain_cfg

    registry = get_middleware_registry()
    instances: list[AgentMiddleware[Any, Any, Any]] = []

    for item in config.get_enabled():
        try:
            cls = registry.resolve(item.name)
            resolved_kwargs = _resolve_kwargs(item.kwargs, app_config)

            # ToolErrorHandlingMiddleware 的 drop_error_from_history 默认跟随 app_config.agent
            if (
                cls is ToolErrorHandlingMiddleware
                and "drop_error_from_history" not in resolved_kwargs
            ):
                resolved_kwargs["drop_error_from_history"] = app_config.agent.drop_error_from_history

            instance = cls(**resolved_kwargs)
            instances.append(instance)
            logger.info("Loaded middleware: %s", item.name)
        except Exception:
            logger.exception("Failed to load middleware '%s', skipping", item.name)

    return instances
