"""通道适配器框架。

提供抽象基类、注册表以及用于 IM 平台集成的消息路由器。
"""

from __future__ import annotations

from scaffold.infra.channels.base import Channel
from scaffold.infra.channels.registry import ChannelRegistry, get_channel_registry
from scaffold.infra.channels.router import ChannelRouter

__all__ = [
    "Channel",
    "ChannelRegistry",
    "ChannelRouter",
    "get_channel_registry",
]
