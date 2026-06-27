"""Slack 通道适配器。

使用 Slack 的 Socket Mode 实现实时消息收发。
安装方式：uv pip install -e ".[channels]"
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.infra.channels.base import Channel

logger = logging.getLogger(__name__)


class SlackChannel(Channel):
    """基于 Socket Mode 的 Slack 通道适配器。

    依赖：
        - slack-sdk>=3.34.0
        - slack-bolt>=1.20.0（用于 Socket Mode）
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._client: Any = None
        self._app: Any = None
        self._bot_token = config.get("bot_token") or ""
        self._app_token = config.get("app_token") or ""

    async def start(self) -> None:
        """启动 Slack Socket Mode 连接。"""
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            logger.error("slack-bolt not installed. Install channels: uv pip install -e '.[channels]'")
            return

        self._app = AsyncApp(token=self._bot_token)

        @self._app.event("message")
        async def handle_message(event: dict[str, Any]) -> None:
            text = event.get("text", "")
            user = event.get("user", "unknown")
            channel = event.get("channel", "unknown")
            thread_ts = event.get("thread_ts") or event.get("ts")
            await self.handle_incoming(user, text, thread_ts or channel)

        handler = AsyncSocketModeHandler(self._app, self._app_token)
        logger.info("Slack channel '%s' starting Socket Mode...", self.name)
        await handler.start_async()

    async def stop(self) -> None:
        """停止 Slack 连接。"""
        logger.info("Slack channel '%s' stopping...", self.name)

    async def send_message(self, user_id: str, text: str, **kwargs: Any) -> None:
        """向 Slack 频道或用户发送消息。"""
        if self._client is None:
            try:
                from slack_sdk.web.async_client import AsyncWebClient

                self._client = AsyncWebClient(token=self._bot_token)
            except ImportError:
                logger.error("slack-sdk not installed")
                return

        channel = kwargs.get("channel", user_id)
        await self._client.chat_postMessage(channel=channel, text=text)
