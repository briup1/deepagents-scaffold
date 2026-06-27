"""工具注册与发现。

支持：
- 通过 config.yaml 中的导入路径加载自定义工具
- 自动发现 plugins/tools/ 目录下的工具
- MCP 工具（未来）
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
    """从 'module.path:function_name' 导入可调用对象。"""
    module_path, attr_name = use_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def load_tool_from_config(tool_config: ToolConfig) -> StructuredTool:
    """根据配置定义加载单个工具。"""
    func = _import_callable(tool_config.use)

    # 从配置或文档字符串推导描述信息
    description = tool_config.description
    if description is None and func.__doc__:
        description = inspect.cleandoc(func.__doc__).split("\n")[0]

    # 包装异步或同步函数
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
    """加载所有已配置的工具。

    Args:
        app_config: 可选的 AppConfig。省略时从磁盘加载。

    Returns:
        StructuredTool 实例列表。
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
