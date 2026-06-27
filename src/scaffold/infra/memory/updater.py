"""Memory updater.

从对话消息中提取事实，由 LLM 驱动。
简化自 deer-flow 的 memory updater。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)


class MemoryUpdater:
    """从对话中提取事实并更新记忆存储。

    Args:
        max_facts: 最多保留的事实数量。
        confidence_threshold: 保留事实的最低置信度。
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
        """从对话消息中提取事实。

        生产环境中会调用 LLM 分析对话。
        此简化版本使用启发式规则。
        """
        facts = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, (HumanMessage, AIMessage)):
                continue

            content = str(getattr(msg, "content", ""))
            if not content:
                continue

            # 简单启发式事实提取
            extracted = self._heuristic_extract(content)
            facts.extend(extracted)

        # 去重并限制数量
        seen = set()
        unique_facts = []
        for f in facts:
            key = f["content"][:50]
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        return unique_facts[: self.max_facts]

    def _heuristic_extract(self, text: str) -> list[dict[str, Any]]:
        """使用简单启发式规则提取潜在事实。"""
        facts = []

        # 偏好模式
        if "i like" in text.lower() or "i prefer" in text.lower():
            facts.append(
                {
                    "content": text.strip(),
                    "category": "preference",
                    "confidence": 0.85,
                    "source": "heuristic",
                }
            )

        # 目标模式
        if "i want to" in text.lower() or "my goal is" in text.lower():
            facts.append(
                {
                    "content": text.strip(),
                    "category": "goal",
                    "confidence": 0.8,
                    "source": "heuristic",
                }
            )

        # 知识模式
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
        """将新事实与已有事实合并，保留置信度最高者。"""
        merged = {f["content"][:50]: f for f in existing}

        for f in new:
            key = f["content"][:50]
            if key in merged:
                # 保留更高置信度
                if f["confidence"] > merged[key]["confidence"]:
                    merged[key] = f
            else:
                merged[key] = f

        # 按阈值过滤并限制数量
        result = [f for f in merged.values() if f["confidence"] >= self.confidence_threshold]
        result.sort(key=lambda x: x["confidence"], reverse=True)
        return result[: self.max_facts]
