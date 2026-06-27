"""Channel 抽象基类。

定义所有 IM 平台适配器必须实现的接口。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Channel(ABC):
    """IM 平台 channel 适配器的抽象基类。

    每个适配器将外部消息平台连接到
    scaffold 的 agent 运行时。
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self._message_handler: Callable[[str, str, str], Any] | None = None

    @abstractmethod
    async def start(self) -> None:
        """启动 channel（连接、开始轮询/webhook）。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止 channel（断开连接、清理）。"""

    @abstractmethod
    async def send_message(self, user_id: str, text: str, **kwargs: Any) -> None:
        """向用户发送文本消息。"""

    def on_message(self, handler: Callable[[str, str, str], Any]) -> None:
        """注册接收消息的处理器。

        Args:
            handler: 接收 (user_id, text, thread_id) 的回调函数。
        """
        self._message_handler = handler

    async def handle_incoming(
        self,
        user_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> None:
        """处理来自平台的一条消息。"""
        if self._message_handler is None:
            logger.warning("No message handler registered for channel '%s'", self.name)
            return
        await self._message_handler(user_id, text, thread_id or "default")
