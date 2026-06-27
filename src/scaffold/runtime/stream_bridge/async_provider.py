"""异步流桥工厂。"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from .base import StreamBridge

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def make_stream_bridge(
    config: dict[str, Any] | None = None,
) -> AsyncIterator[StreamBridge]:
    """异步上下文管理器，生成一个 :class:`StreamBridge`。

    未提供配置时回退到 :class:`MemoryStreamBridge`。
    """
    config = config or {}
    bridge_type = config.get("type", "memory")

    if bridge_type == "memory":
        from .memory import MemoryStreamBridge

        maxsize = int(config.get("queue_maxsize", 256))
        bridge = MemoryStreamBridge(queue_maxsize=maxsize)
        logger.info("Stream bridge initialised: memory (queue_maxsize=%d)", maxsize)
        try:
            yield bridge
        finally:
            await bridge.close()
        return

    if bridge_type == "redis":
        raise NotImplementedError("Redis stream bridge not yet implemented")

    raise ValueError(f"Unknown stream bridge type: {bridge_type!r}")
