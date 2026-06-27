"""提示词模板注册表。

管理具名提示词模板，用于 agent 系统提示词组装。
"""

from __future__ import annotations

from typing import Any


class PromptRegistry:
    """用于管理具名提示词模板的注册表。"""

    def __init__(self) -> None:
        self._templates: dict[str, str] = {}

    def register(self, name: str, template: str) -> None:
        """注册一个具名提示词模板。"""
        self._templates[name] = template

    def get(self, name: str) -> str | None:
        """按名称检索模板。"""
        return self._templates.get(name)

    def list_names(self) -> list[str]:
        """列出所有已注册的模板名称。"""
        return list(self._templates.keys())

    def build(
        self,
        user_prompt: str | None = None,
        base_name: str = "base",
        custom_name: str | None = None,
        suffix_name: str | None = None,
    ) -> str:
        """从具名片段组装提示词。

        顺序: USER -> BASE -> CUSTOM -> SUFFIX
        """
        parts: list[str] = []
        if user_prompt:
            parts.append(user_prompt)

        base = self._templates.get(base_name)
        if custom_name and custom_name in self._templates:
            parts.append(self._templates[custom_name])
        elif base:
            parts.append(base)

        if suffix_name and suffix_name in self._templates:
            parts.append(self._templates[suffix_name])

        return "\n\n".join(parts)
