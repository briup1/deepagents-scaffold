"""Todo list middleware.

Manages a todo list with context-loss detection (when summarization
scrolls out todo history) and premature-exit prevention.

Adapted from deerflow.agents.middlewares.todo_middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class TodoMiddleware(AgentMiddleware):
    """Track todo items and inject reminders when incomplete todos exist.

    Args:
        max_todos: Maximum number of todos to track per thread.
        reminder_threshold: Inject reminder if more than this many todos are incomplete.
    """

    def __init__(
        self,
        *,
        max_todos: int = 20,
        reminder_threshold: int = 1,
    ) -> None:
        self.max_todos = max_todos
        self.reminder_threshold = reminder_threshold

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Inject todo reminder if incomplete todos exist."""
        todos = state.get("_todos", [])
        incomplete = [t for t in todos if not t.get("done", False)]

        if len(incomplete) < self.reminder_threshold:
            return None

        todo_text = "\n".join(
            f"{'[x]' if t.get('done') else '[ ]'} {t.get('title', 'Untitled')}" for t in incomplete[:10]
        )

        reminder = (
            f"<system-reminder>\n"
            f"You have {len(incomplete)} incomplete task(s):\n"
            f"{todo_text}\n"
            f"Complete these tasks before finishing the conversation.\n"
            f"</system-reminder>"
        )

        messages = list(state.get("messages", []))
        messages.append(SystemMessage(content=reminder, name="todo_reminder"))
        return {"messages": messages}

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Async variant."""
        return self.before_model(state, runtime)
