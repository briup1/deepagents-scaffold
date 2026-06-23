"""Channel adapter registry.

Maps platform names to adapter classes for lazy instantiation.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Built-in channel adapter import paths
_DEFAULT_CHANNELS: dict[str, str] = {
    "slack": "scaffold.infra.channels.adapters.slack:SlackChannel",
    "feishu": "scaffold.infra.channels.adapters.feishu:FeishuChannel",
}


class ChannelRegistry:
    """Registry for channel adapter classes."""

    def __init__(self) -> None:
        self._map: dict[str, str] = dict(_DEFAULT_CHANNELS)

    def register(self, name: str, import_path: str) -> None:
        """Register a channel adapter."""
        self._map[name] = import_path
        logger.debug("Registered channel '%s' -> %s", name, import_path)

    def resolve(self, name: str) -> type[Any]:
        """Resolve a channel name to its adapter class."""
        if name not in self._map:
            raise ValueError(f"Unknown channel '{name}'. Known: {list(self._map.keys())}")
        module_path, class_name = self._map[name].split(":")
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def list_known(self) -> list[str]:
        """Return all registered channel names."""
        return list(self._map.keys())


# Singleton
_registry: ChannelRegistry | None = None


def get_channel_registry() -> ChannelRegistry:
    """Get the global channel registry."""
    global _registry
    if _registry is None:
        _registry = ChannelRegistry()
    return _registry
