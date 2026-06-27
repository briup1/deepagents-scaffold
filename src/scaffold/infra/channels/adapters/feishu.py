"""飞书（Lark）通道适配器。

使用飞书的 webhook/机器人 API 进行消息收发。
安装依赖：uv pip install lark-oapi>=1.4.0
"""

from __future__ import annotations

import json
import logging
from typing import Any

from scaffold.infra.channels.base import Channel

logger = logging.getLogger(__name__)


class FeishuChannel(Channel):
    """飞书（Lark）通道适配器，使用机器人 webhook。

    依赖：
        - lark-oapi>=1.4.0
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._app_id = config.get("app_id") or ""
        self._app_secret = config.get("app_secret") or ""
        self._webhook_url = config.get("webhook_url", "")
        self._client: Any = None

    async def start(self) -> None:
        """启动飞书 webhook 监听器。"""
        logger.info("Feishu channel '%s' ready (webhook mode)", self.name)

    async def stop(self) -> None:
        """停止飞书连接。"""
        logger.info("Feishu channel '%s' stopping...", self.name)

    async def send_message(self, user_id: str, text: str, **kwargs: Any) -> None:
        """通过飞书机器人 webhook 发送消息。

        如果配置了 webhook_url，则直接使用；否则需要 lark-oapi SDK。
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

        # 通过 Open API 发送
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
        """通过自定义 webhook URL 发送。"""
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
