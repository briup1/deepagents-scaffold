"""Summarization middleware.

Truncates old messages and replaces history with summaries when the
context window fills up. Extends LangChain's SummarizationMiddleware
with skill preservation hooks.

Adapted from deerflow.agents.middlewares.summarization_middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class SummarizationMiddleware(AgentMiddleware):
    """Summarize conversation history when token count exceeds threshold.

    Args:
        max_context_tokens: Trigger summarization when context exceeds this.
        keep_recent_turns: Number of recent turns to preserve verbatim.
        summary_model_name: Optional model name for summarization (uses default if None).
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
        """Check context size and summarize if needed."""
        messages = list(state.get("messages", []))
        if len(messages) < self.keep_recent_turns * 2:
            return None

        # Simple token estimation (1 token ~= 4 chars for CJK, ~= 4 chars for English)
        total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, "content"))
        estimated_tokens = total_chars // 3

        if estimated_tokens < self.max_context_tokens:
            return None

        thread_id = state.get("configurable", {}).get("thread_id", "default")

        # Keep recent turns, summarize the rest
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
        """Async variant."""
        return self.before_model(state, runtime)


def _summarize_messages(messages: list[Any]) -> str:
    """Create a simple summary from message history.

    In production this should call an LLM for high-quality summarization.
    """
    parts: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = str(getattr(msg, "content", ""))[:200]
        if content:
            parts.append(f"[{role}] {content}")
    return "\n".join(parts[:20])  # Cap summary length
