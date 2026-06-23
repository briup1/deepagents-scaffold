"""Tool registration and discovery.

Supports:
- Custom tools from config.yaml import paths
- Automatic discovery of tools in plugins/tools/
- MCP tools (future)
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.config.tool_config import ToolConfig

logger = logging.getLogger(__name__)

ToolFunc = Callable[..., Any]


def _import_callable(use_path: str) -> ToolFunc:
    """Import a callable from 'module.path:function_name'."""
    module_path, attr_name = use_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def load_tool_from_config(tool_config: ToolConfig) -> StructuredTool:
    """Load a single tool from its config definition."""
    func = _import_callable(tool_config.use)

    # Derive description from config or docstring
    description = tool_config.description
    if description is None and func.__doc__:
        description = inspect.cleandoc(func.__doc__).split("\n")[0]

    # Wrap async or sync function
    if inspect.iscoroutinefunction(func):
        return StructuredTool.from_function(
            coroutine=func,
            name=tool_config.name,
            description=description or tool_config.name,
        )
    return StructuredTool.from_function(
        func=func,
        name=tool_config.name,
        description=description or tool_config.name,
    )


def get_available_tools(app_config: AppConfig | None = None) -> list[StructuredTool]:
    """Load all configured tools.

    Args:
        app_config: Optional AppConfig. Loads from disk if omitted.

    Returns:
        List of StructuredTool instances.
    """
    if app_config is None:
        app_config = get_app_config()

    tools: list[StructuredTool] = []
    for tool_cfg in app_config.tools:
        try:
            tool = load_tool_from_config(tool_cfg)
            tools.append(tool)
            logger.debug("Loaded tool: %s", tool_cfg.name)
        except Exception:
            logger.exception("Failed to load tool: %s", tool_cfg.name)
    return tools
