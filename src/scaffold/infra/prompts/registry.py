"""Prompt template registry.

Manages named prompt templates for agent system prompt assembly.
"""

from __future__ import annotations

from typing import Any


class PromptRegistry:
    """Registry for named prompt templates."""

    def __init__(self) -> None:
        self._templates: dict[str, str] = {}

    def register(self, name: str, template: str) -> None:
        """Register a named prompt template."""
        self._templates[name] = template

    def get(self, name: str) -> str | None:
        """Retrieve a template by name."""
        return self._templates.get(name)

    def list_names(self) -> list[str]:
        """List all registered template names."""
        return list(self._templates.keys())

    def build(
        self,
        user_prompt: str | None = None,
        base_name: str = "base",
        custom_name: str | None = None,
        suffix_name: str | None = None,
    ) -> str:
        """Assemble a prompt from named segments.

        Order: USER -> BASE -> CUSTOM -> SUFFIX
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
