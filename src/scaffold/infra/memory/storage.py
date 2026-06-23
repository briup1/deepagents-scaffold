"""Memory storage backends.

Simple file-based storage for agent memory.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryStorage:
    """Abstract memory storage."""

    async def load(self, key: str) -> dict[str, Any] | None:
        """Load memory data by key."""
        raise NotImplementedError

    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Save memory data by key."""
        raise NotImplementedError


class FileMemoryStorage(MemoryStorage):
    """File-based memory storage with JSON serialization."""

    def __init__(self, base_dir: str = "./data") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def _path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"memory_{safe_key}.json"

    async def load(self, key: str) -> dict[str, Any] | None:
        if key in self._cache:
            return dict(self._cache[key])

        path = self._path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._cache[key] = data
            return data
        except Exception:
            logger.exception("Failed to load memory from %s", path)
            return None

    async def save(self, key: str, data: dict[str, Any]) -> None:
        path = self._path(key)
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._cache[key] = data
            logger.debug("Saved memory to %s", path)
        except Exception:
            logger.exception("Failed to save memory to %s", path)

    def get_facts(self, key: str) -> list[dict[str, Any]]:
        """Get facts from memory."""
        data = self._cache.get(key)
        if not data:
            return []
        return data.get("facts", [])

    def add_fact(self, key: str, fact: dict[str, Any]) -> None:
        """Add a fact to memory."""
        data = self._cache.get(key) or {}
        facts = data.get("facts", [])
        facts.append(fact)
        data["facts"] = facts
        self._cache[key] = data
