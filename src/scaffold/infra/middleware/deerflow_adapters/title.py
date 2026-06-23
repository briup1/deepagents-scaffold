"""Title generation middleware.

Auto-generates conversation titles after the first user message
using a lightweight LLM call.

Adapted from deerflow.agents.middlewares.title_middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class TitleMiddleware(AgentMiddleware):
    """Generate a thread title after the first user message.

    Args:
        max_title_length: Maximum length of generated title.
        model_name: Optional model name for title generation (uses default if None).
    """

    def __init__(
        self,
        *,
        max_title_length: int = 60,
        model_name: str | None = None,
    ) -> None:
        self.max_title_length = max_title_length
        self.model_name = model_name
        self._generated: set[str] = set()

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Generate title after first assistant response."""
        thread_id = state.get("configurable", {}).get("thread_id", "default")

        if thread_id in self._generated:
            return None

        messages = state.get("messages", [])
        if len(messages) < 2:
            return None

        # Find first user message
        user_messages = [m for m in messages if getattr(m, "type", None) == "human"]
        if not user_messages:
            return None

        first_user_text = str(getattr(user_messages[0], "content", ""))[:200]
        if not first_user_text:
            return None

        # Simple heuristic title generation (in production, use LLM)
        title = _generate_title_heuristic(first_user_text, self.max_title_length)
        self._generated.add(thread_id)

        logger.info("Generated title for thread %s: %s", thread_id, title)

        return {"_thread_title": title}

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Async variant."""
        return self.after_model(state, runtime)


def _generate_title_heuristic(text: str, max_length: int) -> str:
    """Generate a concise title from the first user message.

    In production, call a lightweight LLM for better quality.
    """
    # Take first sentence or first N words
    first_sentence = text.split(".")[0].split("\n")[0]
    words = first_sentence.split()[:8]
    title = " ".join(words)

    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title or "New Conversation"
