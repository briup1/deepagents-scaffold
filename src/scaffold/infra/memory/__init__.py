"""Memory system.

Persistent memory with LLM-driven fact extraction, confidence scoring,
and async updates.
"""

from __future__ import annotations

from scaffold.infra.memory.storage import MemoryStorage, FileMemoryStorage
from scaffold.infra.memory.updater import MemoryUpdater

__all__ = [
    "MemoryStorage",
    "FileMemoryStorage",
    "MemoryUpdater",
]
