"""Channel 消息路由器。

将来自 channel 的传入消息路由到对应的 agent。
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.core.agents import create_agent, get_agent
from scaffold.infra.config.app_config import AppConfig, get_app_config

logger = logging.getLogger(__name__)


class ChannelRouter:
    """将 channel 消息路由到 agent，并将响应流式返回。"""

    def __init__(self, app_config: AppConfig | None = None) -> None:
        self.app_config = app_config or get_app_config()

    async def handle_message(
        self,
        user_id: str,
        text: str,
        thread_id: str,
        *,
        agent_name: str = "default",
    ) -> str:
        """处理传入消息并返回 agent 响应。

        Args:
            user_id: 平台特定的用户标识符。
            text: 消息文本。
            thread_id: 会话线程标识符。
            agent_name: 使用的 agent 名称。

        Returns:
            Agent 响应文本。
        """
        try:
            agent = get_agent(agent_name)
        except KeyError:
            agent = create_agent(name=agent_name)

        messages = [{"role": "user", "content": text}]
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            "Channel route | user=%s thread=%s agent=%s",
            user_id,
            thread_id,
            agent_name,
        )

        result = await agent.ainvoke(
            {"messages": messages},
            config=config,
        )

        # 提取响应文本
        response = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and getattr(msg, "type", None) == "ai":
                response = str(msg.content)
                break

        return response or "(no response)"
