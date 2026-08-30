"""Scaffold 中间件框架。

提供注册表 + 工厂，用于从 config.yaml 声明实例化 DeepAgents AgentMiddleware
实例，以及 Deer-Flow 中间件适配器。
"""

from __future__ import annotations

from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.middleware.registry import MiddlewareRegistry, get_middleware_registry

__all__ = [
    "MiddlewareRegistry",
    "get_middleware_registry",
    "build_middleware_chain",
]
