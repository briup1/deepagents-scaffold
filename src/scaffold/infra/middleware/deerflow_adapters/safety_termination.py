"""安全终止中间件。

检测 provider 安全拒绝信号（content_filter、refusal、SAFETY 等）并在执行前
剥离截断的 tool_calls，避免 agent 执行参数不完整的危险操作。

改编自 deerflow.agents.middlewares.safety_finish_reason_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# 已知 provider 安全信号
_DEFAULT_SAFETY_SIGNALS: frozenset[str] = frozenset(
    {
        "content_filter",
        "refusal",
        "SAFETY",
        "safety",
        "blocked",
        "ResponsibleAIPolicyViolation",
    }
)

_USER_FACING_MESSAGE = (
    "The model provider stopped this response with a safety-related signal "
    "({reason_field}={reason_value!r}). Any tool calls produced in this turn "
    "were suppressed because their arguments may be truncated and unsafe to execute. "
    "Please rephrase the request or ask for a narrower output."
)


class SafetyTerminationMiddleware(AgentMiddleware):
    """检测安全终止并优雅处理。

    核心行为：
    1. 只在最后一条消息是 AIMessage 且携带 tool_calls 时才干预；
    2. 命中安全信号后，清空该消息的 tool_calls，阻止后续工具执行；
    3. 向消息 content 追加用户可见解释；
    4. 在 ``additional_kwargs.safety_termination`` 中写入结构化元数据，
       供 SSE 消费者和日志/链路追踪使用。

    Args:
        strip_truncated_tool_calls: 从被拦截的响应中移除 tool_calls。
        emit_warning: 是否向 content 追加解释文本。
        extra_signals: 除默认信号外额外识别的安全信号集合。
    """

    def __init__(
        self,
        *,
        strip_truncated_tool_calls: bool = True,
        emit_warning: bool = True,
        extra_signals: list[str] | set[str] | None = None,
    ) -> None:
        self.strip_truncated_tool_calls = strip_truncated_tool_calls
        self.emit_warning = emit_warning
        self._signals: frozenset[str] = _DEFAULT_SAFETY_SIGNALS | frozenset(extra_signals or ())

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """检查最后一条消息是否包含安全信号，并清理截断的 tool_calls。"""
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if not tool_calls:
            # 没有 tool_calls 时让正常（或部分）文本响应自然流给用户
            return None

        termination = _detect_safety_termination(last_msg, self._signals)
        if termination is None:
            return None

        patched = self._build_patched_message(last_msg, termination, tool_calls)

        thread_id = None
        if runtime is not None and getattr(runtime, "context", None):
            thread_id = runtime.context.get("thread_id") if isinstance(runtime.context, dict) else None

        logger.warning(
            "Provider safety termination detected — suppressed %d tool call(s)",
            len(tool_calls),
            extra={
                "thread_id": thread_id,
                "reason_field": termination["reason_field"],
                "reason_value": termination["reason_value"],
                "suppressed_tool_call_names": [tc.get("name") for tc in tool_calls],
            },
        )

        messages[-1] = patched
        return {"messages": messages}

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步版本。"""
        return self.after_model(state, runtime)

    def _build_patched_message(
        self,
        message: AIMessage,
        termination: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> AIMessage:
        """构建清理后的消息：清空 tool_calls、追加解释、写入元数据。"""
        update: dict[str, Any] = {}

        if self.strip_truncated_tool_calls:
            update["tool_calls"] = []

        if self.emit_warning:
            explanation = _USER_FACING_MESSAGE.format(
                reason_field=termination["reason_field"],
                reason_value=termination["reason_value"],
            )
            update["content"] = _append_user_message(message.content, explanation)

        kwargs = dict(getattr(message, "additional_kwargs", None) or {})
        kwargs["safety_termination"] = {
            "reason_field": termination["reason_field"],
            "reason_value": termination["reason_value"],
            "suppressed_tool_call_count": len(tool_calls),
            "suppressed_tool_call_names": [tc.get("name") or "unknown" for tc in tool_calls],
        }
        update["additional_kwargs"] = kwargs

        return _model_copy(message, update)


def _detect_safety_termination(message: AIMessage, signals: frozenset[str]) -> dict[str, Any] | None:
    """检测消息中是否存在 provider 安全终止信号。"""
    metadata = getattr(message, "response_metadata", {}) or {}
    finish_reason = str(metadata.get("finish_reason", ""))

    if finish_reason and finish_reason in signals:
        return {"reason_field": "finish_reason", "reason_value": finish_reason}

    content = str(message.content or "")
    content_lower = content.lower()
    for sig in signals:
        idx = content_lower.find(sig.lower())
        if idx != -1:
            return {"reason_field": "content", "reason_value": content[idx : idx + len(sig)]}

    # 常见拒绝话术：同时包含 "i cannot" 和 "policy"
    if "i cannot" in content_lower and "policy" in content_lower:
        return {"reason_field": "content", "reason_value": "refusal_pattern"}

    return None


def _append_user_message(content: object, text: str) -> str | list[Any]:
    """向 AIMessage content 追加纯文本解释。

    保持 list-content 结构（例如 Anthropic thinking blocks），避免强制类型转换。
    """
    if content is None or content == "":
        return text
    if isinstance(content, list):
        return [*content, {"type": "text", "text": f"\n\n{text}"}]
    if isinstance(content, str):
        return content + f"\n\n{text}"
    return str(content) + f"\n\n{text}"


def _model_copy(message: AIMessage, update: dict[str, Any]) -> AIMessage:
    """兼容 Pydantic v1/v2 的 model_copy/copy 封装。"""
    copier = getattr(message, "model_copy", None) or getattr(message, "copy", None)
    if copier is None:
        raise TypeError("AIMessage does not support model_copy/copy")
    return copier(update=update)
