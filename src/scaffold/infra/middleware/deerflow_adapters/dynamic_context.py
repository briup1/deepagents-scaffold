"""动态上下文中间件。

在每次模型调用前注入记忆和当前日期/时间，作为 system-reminder 风格的消息。

改编自 deerflow.agents.middlewares.dynamic_context_middleware。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class DynamicContextMiddleware(AgentMiddleware):
    """在每次 LLM 调用前注入动态上下文（日期、记忆摘要）。"""

    def __init__(
        self,
        *,
        inject_date: bool = True,
        inject_memory: bool = True,
        memory_sources: list[str] | None = None,
        timezone_str: str = "UTC",
    ) -> None:
        self.inject_date = inject_date
        self.inject_memory = inject_memory
        self.memory_sources = memory_sources or []
        self.timezone_str = timezone_str

    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """在模型调用前注入上下文提醒。"""
        reminders: list[str] = []

        if self.inject_date:
            now = datetime.now(timezone.utc)
            reminders.append(f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if self.inject_memory and self.memory_sources:
            # 从文件加载记忆（简化版 — 完整实现应使用 MemoryStorage）
            for source in self.memory_sources:
                try:
                    content = _load_memory_source(source)
                    if content:
                        reminders.append(f"Memory context ({source}):\n{content}")
                except Exception:
                    logger.debug("Could not load memory source: %s", source)

        if not reminders:
            return None

        reminder_text = "\n".join(reminders)
        messages = list(state.get("messages", []))
        messages.append(
            HumanMessage(
                content=f"<system-reminder>\n{reminder_text}\n</system-reminder>",
                name="system_reminder",
            )
        )
        return {"messages": messages}

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步版本。"""
        return self.before_model(state, runtime)


def _load_memory_source(source: str) -> str | None:
    """加载记忆源文件。"""
    import os

    # 展开 ~ 和环境变量
    path = os.path.expandvars(os.path.expanduser(source))
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None
