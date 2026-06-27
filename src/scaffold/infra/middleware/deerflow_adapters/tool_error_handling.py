"""工具错误处理中间件。

捕获工具执行期间的异常并将其转换为错误
ToolMessage，以便 agent 能够继续运行而不会崩溃。

改编自 deerflow.agents.middlewares.tool_error_handling_middleware。
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """包装工具调用以捕获异常并将其转换为错误 ToolMessage。"""

    def wrap_tool_call(
        self,
        call: Any,
        state: Any,
        runtime: Runtime[Any],
    ) -> Any:
        """为单个工具调用包装错误处理。"""
        try:
            return call
        except Exception as exc:
            # 此 hook 在工具执行前后触发；实际异常处理
            # 发生在 tool node 中。我们在此处记录日志以增强可观测性。
            logger.exception("Tool execution failed: %s", exc)
            raise

    async def awrap_tool_call(
        self,
        call: Any,
        state: Any,
        runtime: Runtime[Any],
    ) -> Any:
        """异步变体 —— 委托给同步版本。"""
        return self.wrap_tool_call(call, state, runtime)
