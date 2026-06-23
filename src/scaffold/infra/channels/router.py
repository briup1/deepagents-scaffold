"""Channel message router.

Routes incoming messages from channels to the appropriate agent.
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.core.agents import create_agent, get_agent
from scaffold.infra.config.app_config import AppConfig, get_app_config

logger = logging.getLogger(__name__)


class ChannelRouter:
    """Routes channel messages to agents and streams responses back."""

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
        """Handle an incoming message and return the agent response.

        Args:
            user_id: Platform-specific user identifier.
            text: Message text.
            thread_id: Conversation thread identifier.
            agent_name: Which agent to use.

        Returns:
            Agent response text.
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

        # Extract response text
        response = ""
        for msg in result.get("messages", []):
            if hasattr(msg, "content") and getattr(msg, "type", None) == "ai":
                response = str(msg.content)
                break

        return response or "(no response)"
