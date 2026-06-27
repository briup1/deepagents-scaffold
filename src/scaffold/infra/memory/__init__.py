"""Memory system.

持久化记忆，支持 LLM 驱动的事实提取、置信度评分与异步更新。
"""

from __future__ import annotations

from scaffold.infra.memory.storage import MemoryStorage, FileMemoryStorage
from scaffold.infra.memory.updater import MemoryUpdater

__all__ = [
    "MemoryStorage",
    "FileMemoryStorage",
    "MemoryUpdater",
]
