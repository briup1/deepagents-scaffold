"""Feishu (Lark) channel adapter.

Uses Feishu's webhook/bot API for messaging.
Install with: uv pip install lark-oapi>=1.4.0
"""

from __future__ import annotations

import json
import logging
from typing import Any

from scaffold.infra.channels.base import Channel

logger = logging.getLogger(__name__)


class FeishuChannel(Channel):
    """Feishu (Lark) channel adapter using bot webhook.

    Requires:
        - lark-oapi>=1.4.0
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id = config.get("app_id") or ""
        self._app_secret = config.get("app_secret") or ""
        self._webhook_url = config.get("webhook_url", "")
        self._client: Any = None

    async def start(self) -> None:
        """Start Feishu webhook listener."""
        logger.info("Feishu channel '%s' ready (webhook mode)", self.name)

    async def stop(self) -> None:
        """Stop Feishu connection."""
        logger.info("Feishu channel '%s' stopping...", self.name)

    async def send_message(self, user_id: str, text: str, **kwargs: Any) -> None:
        """Send a message via Feishu bot webhook.

        If webhook_url is configured, uses it directly.
        Otherwise requires lark-oapi SDK.
        """
        if self._webhook_url:
            await self._send_via_webhook(user_id, text)
            return

        try:
            from lark_oapi import Client
        except ImportError:
            logger.error("lark-oapi not installed. Install channels: uv pip install -e '.[channels]'")
            return

        if self._client is None:
            self._client = Client.builder().app_id(self._app_id).app_secret(self._app_secret).build()

        # Send via Open API
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            req = (
                CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .receive_id(user_id)
                .body(CreateMessageRequestBody.builder().msg_type("text").content(json.dumps({"text": text})).build())
                .build()
            )
            resp = await self._client.im.v1.message.acreate(req)
            if not resp.success():
                logger.error("Feishu send failed: %s", resp.msg)
        except Exception:
            logger.exception("Failed to send Feishu message")

    async def _send_via_webhook(self, user_id: str, text: str) -> None:
        """Send via custom webhook URL."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    self._webhook_url,
                    json={
                        "msg_type": "text",
                        "content": {"text": text},
                    },
                    timeout=30.0,
                )
        except Exception:
            logger.exception("Feishu webhook send failed")
