"""Middleware factory.

Builds AgentMiddleware instances from MiddlewareConfig declarations.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.config.middleware_config import MiddlewareChainConfig
from scaffold.infra.middleware.registry import get_middleware_registry

logger = logging.getLogger(__name__)


def _resolve_kwargs(kwargs: dict[str, Any], app_config: AppConfig) -> dict[str, Any]:
    """Resolve configuration references in middleware kwargs.

    Supports:
    - $config.memory — injects MemoryConfig dict
    - $config.models[0] — injects first ModelConfig dict
    - $env.VAR_NAME — environment variable
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
    """Resolve a dotted config attribute path."""
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
    """Build an ordered list of AgentMiddleware instances from config.

    Args:
        config: Middleware chain config. Loaded from app_config if omitted.
        app_config: AppConfig for resolving $config references.

    Returns:
        Ordered list of middleware instances for create_deep_agent(middleware=...).
    """
    if app_config is None:
        app_config = get_app_config()

    if config is None:
        # Try to get from app_config; fallback to empty chain
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
            instance = cls(**resolved_kwargs)
            instances.append(instance)
            logger.info("Loaded middleware: %s", item.name)
        except Exception:
            logger.exception("Failed to load middleware '%s', skipping", item.name)

    return instances
