"""动态上下文中间件。

在每次模型调用前把当前日期/时间注入 system message，
让模型看到但不写回 state.messages，避免 AG-UI/CopilotKit 把提醒渲染成聊天消息。

改编自 deerflow.agents.middlewares.dynamic_context_middleware。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class DynamicContextMiddleware(AgentMiddleware):
    """在每次 LLM 调用前注入动态上下文（当前日期/时间）。"""

    def __init__(
        self,
        *,
        inject_date: bool = True,
        timezone_str: str = "UTC",
    ) -> None:
        self.inject_date = inject_date
        self.timezone_str = timezone_str

    def _build_reminder_text(self, state: Any) -> str:
        """构造日期提醒文本。"""
        reminders: list[str] = []

        if self.inject_date:
            now = datetime.now(timezone.utc)
            reminders.append(f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        return "\n\n".join(reminders)

    def _inject_request(self, request: Any) -> Any:
        """把提醒合并进当前请求的 system_message，不修改 state。"""
        reminder_text = self._build_reminder_text(request.state)
        if not reminder_text:
            return request

        existing = request.system_message
        existing_text = existing.text if existing is not None else ""
        if existing_text:
            new_text = f"{existing_text}\n\n[系统上下文]\n{reminder_text}"
        else:
            new_text = f"[系统上下文]\n{reminder_text}"

        return request.override(system_message=SystemMessage(content=new_text))

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """同步调用：注入上下文后交给模型。"""
        return handler(self._inject_request(request))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        """异步调用：注入上下文后交给模型。"""
        return await handler(self._inject_request(request))

    # 保留旧钩子空实现，防止链中其他组件仍按 before_model 调用时出错。
    # DeepAgents 实际会优先使用 wrap_model_call/awrap_model_call。
    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        return None

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        return None
