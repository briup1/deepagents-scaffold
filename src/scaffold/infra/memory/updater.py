"""Memory updater.

LLM-driven fact extraction from conversation messages.
Simplified from deer-flow's memory updater.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)


class MemoryUpdater:
    """Extract facts from conversation and update memory storage.

    Args:
        max_facts: Maximum number of facts to retain.
        confidence_threshold: Minimum confidence to keep a fact.
    """

    def __init__(
        self,
        *,
        max_facts: int = 100,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.max_facts = max_facts
        self.confidence_threshold = confidence_threshold

    def extract_facts(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Extract facts from conversation messages.

        In production, this calls an LLM to analyze the conversation.
        This simplified version uses heuristics.
        """
        facts = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, (HumanMessage, AIMessage)):
                continue

            content = str(getattr(msg, "content", ""))
            if not content:
                continue

            # Simple heuristic fact extraction
            extracted = self._heuristic_extract(content)
            facts.extend(extracted)

        # Deduplicate and limit
        seen = set()
        unique_facts = []
        for f in facts:
            key = f["content"][:50]
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        return unique_facts[: self.max_facts]

    def _heuristic_extract(self, text: str) -> list[dict[str, Any]]:
        """Extract potential facts using simple heuristics."""
        facts = []

        # Preference patterns
        if "i like" in text.lower() or "i prefer" in text.lower():
            facts.append(
                {
                    "content": text.strip(),
                    "category": "preference",
                    "confidence": 0.85,
                    "source": "heuristic",
                }
            )

        # Goal patterns
        if "i want to" in text.lower() or "my goal is" in text.lower():
            facts.append(
                {
                    "content": text.strip(),
                    "category": "goal",
                    "confidence": 0.8,
                    "source": "heuristic",
                }
            )

        # Knowledge patterns
        if "i know" in text.lower() or "i understand" in text.lower():
            facts.append(
                {
                    "content": text.strip(),
                    "category": "knowledge",
                    "confidence": 0.75,
                    "source": "heuristic",
                }
            )

        return facts

    def merge_facts(
        self,
        existing: list[dict[str, Any]],
        new: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge new facts with existing, keeping highest confidence."""
        merged = {f["content"][:50]: f for f in existing}

        for f in new:
            key = f["content"][:50]
            if key in merged:
                # Keep higher confidence
                if f["confidence"] > merged[key]["confidence"]:
                    merged[key] = f
            else:
                merged[key] = f

        # Filter by threshold and limit
        result = [f for f in merged.values() if f["confidence"] >= self.confidence_threshold]
        result.sort(key=lambda x: x["confidence"], reverse=True)
        return result[: self.max_facts]
