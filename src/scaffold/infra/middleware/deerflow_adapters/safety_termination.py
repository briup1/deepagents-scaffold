"""安全终止中间件。

检测 provider 安全拒绝信号（content_filter、refusal、SAFETY）
并在执行前剥离截断的 tool_calls。

改编自 deerflow.agents.middlewares.safety_finish_reason_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# 已知 provider 安全信号
_SAFETY_SIGNALS = {
    "content_filter",
    "refusal",
    "SAFETY",
    "safety",
    "blocked",
    "ResponsibleAIPolicyViolation",
}


class SafetyTerminationMiddleware(AgentMiddleware):
    """检测安全终止并优雅处理。

    Args:
        strip_truncated_tool_calls: 从被拦截的响应中移除不完整的 tool_calls。
        emit_warning: 检测到安全拦截时注入一条系统警告消息。
    """

    def __init__(
        self,
        *,
        strip_truncated_tool_calls: bool = True,
        emit_warning: bool = True,
    ) -> None:
        self.strip_truncated_tool_calls = strip_truncated_tool_calls
        self.emit_warning = emit_warning

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """检查最后一条消息是否包含安全信号。"""
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        # 在 response_metadata 中检查安全信号
        metadata = getattr(last_msg, "response_metadata", {}) or {}
        finish_reason = metadata.get("finish_reason", "")
        model_name = metadata.get("model_name", "")

        # 同时检查内容中的拒绝模式
        content = str(last_msg.content or "")
        is_safety = (
            finish_reason in _SAFETY_SIGNALS
            or any(sig in content.lower() for sig in _SAFETY_SIGNALS)
            or "i cannot" in content.lower()
            and "policy" in content.lower()
        )

        if not is_safety:
            return None

        logger.warning("Safety termination detected: finish_reason=%s model=%s", finish_reason, model_name)

        updates: dict[str, Any] = {}

        # 剥离截断的 tool calls
        if self.strip_truncated_tool_calls and hasattr(last_msg, "tool_calls"):
            tool_calls = last_msg.tool_calls
            if tool_calls:
                # 从消息中移除 tool_calls，防止执行
                stripped_msg = AIMessage(content=last_msg.content)
                messages[-1] = stripped_msg
                updates["messages"] = messages
                logger.debug("Stripped %d tool_calls from safety-blocked response", len(tool_calls))

        # 发出警告
        if self.emit_warning:
            warning = SystemMessage(
                content="WARNING: The previous response was blocked by a safety filter. "
                "Avoid generating harmful content. If this was a mistake, rephrase your request."
            )
            updates["messages"] = [*messages, warning]

        return updates

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步版本。"""
        return self.after_model(state, runtime)
