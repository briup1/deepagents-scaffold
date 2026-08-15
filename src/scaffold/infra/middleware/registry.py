"""Middleware 注册表。

将人类可读的名字映射到 AgentMiddleware 类，使得 config.yaml 可以通过别名而非完整导入路径声明 middleware。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

logger = logging.getLogger(__name__)

# 已知内置 middleware 别名 -> 导入路径
_DEFAULT_MIDDLEWARE_MAP: dict[str, str] = {
    # DeepAgents 内置 middleware
    "MemoryMiddleware": "deepagents.middleware.memory:MemoryMiddleware",
    "FilesystemMiddleware": "deepagents.middleware.filesystem:FilesystemMiddleware",
    "SubAgentMiddleware": "deepagents.middleware.subagents:SubAgentMiddleware",
    "AsyncSubAgentMiddleware": "deepagents.middleware.async_subagents:AsyncSubAgentMiddleware",
    "SkillsMiddleware": "deepagents.middleware.skills:SkillsMiddleware",
    "RubricMiddleware": "deepagents.middleware.rubric:RubricMiddleware",
    "SummarizationMiddleware": "deepagents.middleware.summarization:SummarizationMiddleware",
    # Deer-Flow scaffold middleware 适配器
    "LoopDetectionMiddleware": "scaffold.infra.middleware.deerflow_adapters.loop_detection:LoopDetectionMiddleware",
    "ToolErrorHandlingMiddleware": "scaffold.infra.middleware.deerflow_adapters.tool_error_handling:ToolErrorHandlingMiddleware",
    "DynamicContextMiddleware": "scaffold.infra.middleware.deerflow_adapters.dynamic_context:DynamicContextMiddleware",
    "TokenUsageMiddleware": "scaffold.infra.middleware.deerflow_adapters.token_usage:TokenUsageMiddleware",
    "SafetyTerminationMiddleware": "scaffold.infra.middleware.deerflow_adapters.safety_termination:SafetyTerminationMiddleware",
    "InputGuardrailMiddleware": "scaffold.infra.middleware.deerflow_adapters.input_guardrail:InputGuardrailMiddleware",
    "TodoMiddleware": "scaffold.infra.middleware.deerflow_adapters.todo:TodoMiddleware",
    "TitleMiddleware": "scaffold.infra.middleware.deerflow_adapters.title:TitleMiddleware",
    "DeepAgentsSummarizationMiddleware": "scaffold.infra.middleware.deerflow_adapters.deepagents_summarization:DeepAgentsSummarizationMiddleware",
    "ModelRetryMiddleware": "scaffold.infra.middleware.deerflow_adapters.model_retry:ModelRetryAdapter",
    "ToolRetryMiddleware": "scaffold.infra.middleware.deerflow_adapters.tool_retry:ToolRetryAdapter",
    "ModelFallbackMiddleware": "scaffold.infra.middleware.deerflow_adapters.model_fallback:ModelFallbackAdapter",
}


class MiddlewareRegistry:
    """用于 middleware 类解析的注册表。"""

    def __init__(self) -> None:
        self._map: dict[str, str] = dict(_DEFAULT_MIDDLEWARE_MAP)

    def register(self, alias: str, import_path: str) -> None:
        """注册新的 middleware 别名。

        Args:
            alias: 在 config.yaml 中使用的人类可读名称。
            import_path: 点分导入路径，例如 'mymodule:MyMiddleware'。
        """
        self._map[alias] = import_path
        logger.debug("Registered middleware alias '%s' -> %s", alias, import_path)

    def resolve(self, alias: str) -> type[AgentMiddleware[Any, Any, Any]]:
        """将别名解析为 middleware 类。

        Args:
            alias: 来自 config.yaml 的 middleware 名称。

        Returns:
            middleware 类。

        Raises:
            ValueError: 如果别名未知。
        """
        # 如果别名包含冒号，则视为直接导入路径
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
        """返回所有已注册的别名。"""
        return list(self._map.keys())


# 单例注册表实例
_registry: MiddlewareRegistry | None = None


def get_middleware_registry() -> MiddlewareRegistry:
    """获取全局 middleware 注册表。"""
    global _registry
    if _registry is None:
        _registry = MiddlewareRegistry()
    return _registry
