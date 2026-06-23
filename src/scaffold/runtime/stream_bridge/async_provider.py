"""Async stream bridge factory."""

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
    """Async context manager that yields a :class:`StreamBridge`.

    Falls back to :class:`MemoryStreamBridge` when no configuration is provided.
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
