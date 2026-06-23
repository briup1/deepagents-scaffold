"""Middleware registry.

Maps human-readable names to AgentMiddleware classes so config.yaml can
declare middleware by alias rather than full import path.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware

logger = logging.getLogger(__name__)

# Known built-in middleware aliases -> import path
_DEFAULT_MIDDLEWARE_MAP: dict[str, str] = {
    # DeepAgents built-in middleware
    "MemoryMiddleware": "deepagents.middleware.memory:MemoryMiddleware",
    "FilesystemMiddleware": "deepagents.middleware.filesystem:FilesystemMiddleware",
    "SubAgentMiddleware": "deepagents.middleware.subagents:SubAgentMiddleware",
    "AsyncSubAgentMiddleware": "deepagents.middleware.async_subagents:AsyncSubAgentMiddleware",
    "SkillsMiddleware": "deepagents.middleware.skills:SkillsMiddleware",
    "RubricMiddleware": "deepagents.middleware.rubric:RubricMiddleware",
    "SummarizationMiddleware": "deepagents.middleware.summarization:SummarizationMiddleware",
    # Deer-Flow scaffold middleware adapters
    "LoopDetectionMiddleware": "scaffold.infra.middleware.deerflow_adapters.loop_detection:LoopDetectionMiddleware",
    "ToolErrorHandlingMiddleware": "scaffold.infra.middleware.deerflow_adapters.tool_error_handling:ToolErrorHandlingMiddleware",
    "DynamicContextMiddleware": "scaffold.infra.middleware.deerflow_adapters.dynamic_context:DynamicContextMiddleware",
    "TokenUsageMiddleware": "scaffold.infra.middleware.deerflow_adapters.token_usage:TokenUsageMiddleware",
    "SafetyTerminationMiddleware": "scaffold.infra.middleware.deerflow_adapters.safety_termination:SafetyTerminationMiddleware",
    "TodoMiddleware": "scaffold.infra.middleware.deerflow_adapters.todo:TodoMiddleware",
    "TitleMiddleware": "scaffold.infra.middleware.deerflow_adapters.title:TitleMiddleware",
}


class MiddlewareRegistry:
    """Registry for middleware class resolution."""

    def __init__(self) -> None:
        self._map: dict[str, str] = dict(_DEFAULT_MIDDLEWARE_MAP)

    def register(self, alias: str, import_path: str) -> None:
        """Register a new middleware alias.

        Args:
            alias: Human-readable name used in config.yaml.
            import_path: Dotted import path, e.g. 'mymodule:MyMiddleware'.
        """
        self._map[alias] = import_path
        logger.debug("Registered middleware alias '%s' -> %s", alias, import_path)

    def resolve(self, alias: str) -> type[AgentMiddleware[Any, Any, Any]]:
        """Resolve an alias to a middleware class.

        Args:
            alias: Middleware name from config.yaml.

        Returns:
            The middleware class.

        Raises:
            ValueError: If the alias is unknown.
        """
        # If alias contains a colon, treat as direct import path
        if ":" in alias:
            import_path = alias
        else:
            import_path = self._map.get(alias)
            if import_path is None:
                raise ValueError(f"Unknown middleware alias '{alias}'. Known aliases: {list(self._map.keys())}")

        module_path, class_name = import_path.split(":")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not issubclass(cls, AgentMiddleware):
            raise TypeError(f"Resolved class {cls} is not an AgentMiddleware subclass")
        return cls

    def list_known(self) -> list[str]:
        """Return all registered aliases."""
        return list(self._map.keys())


# Singleton registry instance
_registry: MiddlewareRegistry | None = None


def get_middleware_registry() -> MiddlewareRegistry:
    """Get the global middleware registry."""
    global _registry
    if _registry is None:
        _registry = MiddlewareRegistry()
    return _registry
