"""Prompt assembler.

Assembles system prompts following DeepAgents convention:
USER -> BASE -> CUSTOM -> SUFFIX.

This matches the assembly order documented in deepagents.graph.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from scaffold.infra.prompts.loader import PromptLoader
from scaffold.infra.prompts.registry import PromptRegistry


class PromptAssembler:
    """Assemble system prompts from template segments."""

    def __init__(self) -> None:
        self.registry = PromptRegistry()
        self._loaded = False

    def load_defaults(self) -> None:
        """Load default templates from the templates directory."""
        if self._loaded:
            return
        loader = PromptLoader()
        loader.load_all(self.registry)
        self._loaded = True

    def assemble(
        self,
        *,
        user: str | None = None,
        base: str | None = None,
        custom: str | None = None,
        suffix: str | None = None,
    ) -> str:
        """Assemble a prompt string.

        Args:
            user: USER segment (front, caller instructions).
            base: BASE segment (default behavior).
            custom: CUSTOM segment (replaces BASE if provided).
            suffix: SUFFIX segment (appended last, model tuning).

        Returns:
            Assembled prompt text.
        """
        self.load_defaults()

        parts: list[str] = []
        if user:
            parts.append(user)

        effective_base = custom or base or self.registry.get("base")
        if effective_base:
            parts.append(effective_base)

        if suffix:
            parts.append(suffix)

        return "\n\n".join(parts)

    def assemble_system_message(
        self,
        *,
        user: str | None = None,
        base: str | None = None,
        custom: str | None = None,
        suffix: str | None = None,
    ) -> SystemMessage:
        """Assemble a SystemMessage from segments."""
        text = self.assemble(user=user, base=base, custom=custom, suffix=suffix)
        return SystemMessage(content=text)
