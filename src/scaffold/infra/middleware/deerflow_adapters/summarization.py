"""Summarization middleware.

在上下文窗口填满时截断旧消息并用摘要替换历史记录。
扩展 LangChain 的 SummarizationMiddleware，增加技能保留钩子。

改编自 deerflow.agents.middlewares.summarization_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class SummarizationMiddleware(AgentMiddleware):
    """当 token 数量超过阈值时，对对话历史进行摘要。

    Args:
        max_context_tokens: 当上下文超过此值时触发摘要。
        keep_recent_turns: 保留最近多少轮对话原文。
        summary_model_name: 用于摘要的可选模型名称（None 则使用默认模型）。
    """

    def __init__(
        self,
        *,
        max_context_tokens: int = 8000,
        keep_recent_turns: int = 4,
        summary_model_name: str | None = None,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.keep_recent_turns = keep_recent_turns
        self.summary_model_name = summary_model_name
        self._summaries: dict[str, str] = {}

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """检查上下文大小，必要时进行摘要。"""
        messages = list(state.get("messages", []))
        if len(messages) < self.keep_recent_turns * 2:
            return None

        # 简单估算 token（1 token 约等于 4 个字符，对 CJK 和英文均适用）
        total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, "content"))
        estimated_tokens = total_chars // 3

        if estimated_tokens < self.max_context_tokens:
            return None

        thread_id = state.get("configurable", {}).get("thread_id", "default")

        # 保留最近轮次，对其余部分进行摘要
        cutoff = len(messages) - self.keep_recent_turns * 2
        to_summarize = messages[:cutoff]
        recent = messages[cutoff:]

        summary_text = _summarize_messages(to_summarize)
        self._summaries[thread_id] = summary_text

        logger.info(
            "Summarized %d messages -> %d chars for thread %s",
            len(to_summarize),
            len(summary_text),
            thread_id,
        )

        new_messages = [
            SystemMessage(content=f"Previous conversation summary:\n{summary_text}"),
            *recent,
        ]
        return {"messages": new_messages}

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步版本。"""
        return self.before_model(state, runtime)


def _summarize_messages(messages: list[Any]) -> str:
    """从消息历史创建简单摘要。

    在生产环境中应调用 LLM 以生成高质量摘要。
    """
    parts: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = str(getattr(msg, "content", ""))[:200]
        if content:
            parts.append(f"[{role}] {content}")
    return "\n".join(parts[:20])  # 限制摘要长度
