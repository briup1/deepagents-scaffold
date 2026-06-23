"""Scaffold middleware framework.

Provides a registry + factory for instantiating DeepAgents AgentMiddleware
instances from config.yaml declarations, plus Deer-Flow middleware adapters.
"""

from __future__ import annotations

from scaffold.infra.middleware.registry import MiddlewareRegistry, get_middleware_registry
from scaffold.infra.middleware.factory import build_middleware_chain

__all__ = [
    "MiddlewareRegistry",
    "get_middleware_registry",
    "build_middleware_chain",
]
