"""通道适配器框架。

提供抽象基类与用于 IM 平台集成的注册表。
"""

from __future__ import annotations

from scaffold.infra.channels.base import Channel
from scaffold.infra.channels.registry import ChannelRegistry, get_channel_registry

__all__ = [
    "Channel",
    "ChannelRegistry",
    "get_channel_registry",
]
