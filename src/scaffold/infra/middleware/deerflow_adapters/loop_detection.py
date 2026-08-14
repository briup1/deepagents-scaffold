"""循环检测中间件。

检测重复的工具调用模式，并在 agent 进入无限循环前将其中断。

改编自 deerflow.agents.middlewares.loop_detection_middleware。
"""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


_HARD_STOP_WARNING = (
    "WARNING: You appear to be in a loop. Stop repeating the same tool calls "
    "and provide a final answer or ask the user for clarification."
)


_PER_TOOL_WARNING_TEMPLATE = (
    "WARNING: You have called '{tool}' {count} times. Avoid redundant calls and summarize your findings."
)


def _append_to_content(content: object, text: str) -> str | list[Any]:
    """向消息 content 追加文本，保持列表/字符串结构。"""
    if content is None or content == "":
        return text
    if isinstance(content, list):
        return [*content, {"type": "text", "text": f"\n\n{text}"}]
    if isinstance(content, str):
        return content + f"\n\n{text}"
    return str(content) + f"\n\n{text}"


def _patch_ai_message(message: AIMessage, *, warning: str) -> AIMessage:
    """构造一条 tool_calls 已清空并附加警告文本的 AIMessage。"""
    copier = getattr(message, "model_copy", None) or getattr(message, "copy", None)
    if copier is None:
        raise TypeError("AIMessage does not support model_copy/copy")
    return copier(
        update={
            "tool_calls": [],
            "content": _append_to_content(message.content, warning),
        }
    )


class LoopDetectionMiddleware(AgentMiddleware):
    """检测重复的工具调用模式并发出警告/中断。

    使用双层检测策略：
    1. 相同调用集合哈希 — 重复 N 次后警告，M 次后强制停止。
    2. 单工具频率计数 — 高频时警告。
    """

    def __init__(
        self,
        *,
        warn_threshold: int = 3,
        hard_stop_threshold: int = 5,
        window_size: int = 10,
        per_tool_warn: int = 30,
        per_tool_hard: int = 50,
    ) -> None:
        self.warn_threshold = warn_threshold
        self.hard_stop_threshold = hard_stop_threshold
        self.window_size = window_size
        self.per_tool_warn = per_tool_warn
        self.per_tool_hard = per_tool_hard

    def before_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """在 thread 上初始化循环追踪状态。"""
        return {
            "_loop_history": deque(maxlen=self.window_size),
            "_loop_counts": {},
            "_loop_warnings": 0,
        }

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """每次模型响应后检查循环。"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        # 对工具调用签名进行哈希
        call_keys = [tc.get("name", str(tc)) for tc in tool_calls]
        call_str = ",".join(sorted(call_keys))
        call_hash = hashlib.sha256(call_str.encode()).hexdigest()[:16]

        loop_history: deque[str] = state.get("_loop_history", deque(maxlen=self.window_size))
        loop_counts: dict[str, int] = state.get("_loop_counts", {})

        # 追踪相同调用集合的重复次数
        loop_history.append(call_hash)
        identical_count = sum(1 for h in loop_history if h == call_hash)

        # 追踪单工具频率
        for key in call_keys:
            loop_counts[key] = loop_counts.get(key, 0) + 1

        updates: dict[str, Any] = {
            "_loop_history": loop_history,
            "_loop_counts": loop_counts,
        }

        if identical_count >= self.hard_stop_threshold:
            logger.warning(
                "Loop detected: identical call set repeated %d times. Stopping agent.",
                identical_count,
            )
            # 清空最后 AI 消息的 tool_calls，避免 assistant tool_calls 与后续 ToolMessage
            # 之间被非 tool 消息隔断，导致 OpenAI/DeepSeek 400 错误。
            patched_last = _patch_ai_message(last_msg, warning=_HARD_STOP_WARNING)
            return {
                **updates,
                "messages": [*messages[:-1], patched_last],
            }

        if identical_count >= self.warn_threshold:
            logger.warning(
                "Potential loop: identical call set repeated %d times.",
                identical_count,
            )

        # 检查单工具频率
        for key, count in loop_counts.items():
            if count >= self.per_tool_hard:
                logger.warning("Tool '%s' called %d times — possible loop.", key, count)
                patched_last = _patch_ai_message(
                    last_msg,
                    warning=_PER_TOOL_WARNING_TEMPLATE.format(tool=key, count=count),
                )
                return {
                    **updates,
                    "messages": [*messages[:-1], patched_last],
                }
            elif count >= self.per_tool_warn:
                logger.warning("Tool '%s' called %d times.", key, count)

        return updates

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步变体。"""
        return self.after_model(state, runtime)
