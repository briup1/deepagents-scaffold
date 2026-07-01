"""工具错误处理中间件。

改编自 deerflow.agents.middlewares.tool_error_handling_middleware。

本中间件实现两个关键防御策略：
1. **工具异常捕获**（wrap_tool_call）：将工具执行异常转换为 error 状态
   ToolMessage，让 agent 继续运行而不崩溃。
2. **错误不入历史**（after_model）：检测模型层返回的 error 响应（如
   finish_reason == "error"），将其从对话历史中剔除，防止"毒消息→永久
   400"死循环（参考 nanobot issue #1303）。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """捕获工具异常并防止错误响应污染对话历史。

    Args:
        drop_error_from_history: 是否从 state.messages 中剔除 error 响应。
            默认 True，防止毒消息死循环。
    """

    def __init__(self, *, drop_error_from_history: bool = True) -> None:
        self.drop_error_from_history = drop_error_from_history

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> Any:
        """包装工具调用，将异常转换为 error ToolMessage。"""
        try:
            return handler(request)
        except Exception as exc:
            logger.exception(
                "Tool '%s' execution failed: %s",
                request.tool_call.get("name", "unknown"),
                exc,
            )
            return ToolMessage(
                content=f"Error: {type(exc).__name__}: {exc}",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> Any:
        """异步变体 —— 包装工具调用，将异常转换为 error ToolMessage。"""
        try:
            return await handler(request)
        except Exception as exc:
            logger.exception(
                "Tool '%s' execution failed: %s",
                request.tool_call.get("name", "unknown"),
                exc,
            )
            return ToolMessage(
                content=f"Error: {type(exc).__name__}: {exc}",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """检查模型响应是否包含 error finish_reason，若是则剔除。

        参考 nanobot 的防御策略：error 响应只返回给用户，不写入 session
        messages，避免"毒消息→永久 400"死循环。
        """
        if not self.drop_error_from_history:
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_msg = messages[-1]
        # 检查 finish_reason 或 response_metadata 中的错误信号
        finish_reason = ""
        if hasattr(last_msg, "response_metadata"):
            finish_reason = str(last_msg.response_metadata.get("finish_reason", ""))

        is_error = finish_reason == "error" or (
            hasattr(last_msg, "status") and getattr(last_msg, "status", None) == "error"
        )

        if not is_error:
            return None

        logger.warning(
            "Error response detected (finish_reason=%s). Dropping from history to prevent poison loop.",
            finish_reason,
        )

        # 剔除最后一条 error 消息
        cleaned = messages[:-1]
        return {"messages": cleaned}
