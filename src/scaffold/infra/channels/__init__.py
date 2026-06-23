"""Channel adapter framework.

Provides abstract base class, registry, and message router for
IM platform integrations.
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
