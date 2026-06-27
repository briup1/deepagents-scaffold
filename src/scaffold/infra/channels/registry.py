"""通道适配器注册表。

将平台名称映射到适配器类，以实现延迟实例化。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 内置通道适配器导入路径
_DEFAULT_CHANNELS: dict[str, str] = {
    "slack": "scaffold.infra.channels.adapters.slack:SlackChannel",
    "feishu": "scaffold.infra.channels.adapters.feishu:FeishuChannel",
}


class ChannelRegistry:
    """通道适配器类的注册表。"""

    def __init__(self) -> None:
        self._map: dict[str, str] = dict(_DEFAULT_CHANNELS)

    def register(self, name: str, import_path: str) -> None:
        """注册一个通道适配器。"""
        self._map[name] = import_path
        logger.debug("Registered channel '%s' -> %s", name, import_path)

    def resolve(self, name: str) -> type[Any]:
        """将通道名称解析为其适配器类。"""
        if name not in self._map:
            raise ValueError(f"Unknown channel '{name}'. Known: {list(self._map.keys())}")
        module_path, class_name = self._map[name].split(":")
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def list_known(self) -> list[str]:
        """返回所有已注册的通道名称。"""
        return list(self._map.keys())


# 单例
_registry: ChannelRegistry | None = None


def get_channel_registry() -> ChannelRegistry:
    """获取全局通道注册表。"""
    global _registry
    if _registry is None:
        _registry = ChannelRegistry()
    return _registry
