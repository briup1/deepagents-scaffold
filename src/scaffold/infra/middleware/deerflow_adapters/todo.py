"""Todo list middleware.

管理待办列表，支持上下文丢失检测（当摘要滚动导致待办历史被移出时）
以及过早退出预防。

改编自 deerflow.agents.middlewares.todo_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class TodoMiddleware(AgentMiddleware):
    """跟踪待办事项，并在存在未完成的待办时注入提醒。

    Args:
        max_todos: 每个线程最多跟踪的待办数量。
        reminder_threshold: 当未完成的待办超过此数量时注入提醒。
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
        """如果存在未完成的待办，注入待办提醒。"""
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
        """异步版本。"""
        return self.before_model(state, runtime)
