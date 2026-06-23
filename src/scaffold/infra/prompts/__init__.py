"""Prompt engineering system.

Template registry, loader, and assembler following DeepAgents
prompt assembly convention: USER -> BASE -> CUSTOM -> SUFFIX.
"""

from __future__ import annotations

from scaffold.infra.prompts.assembler import PromptAssembler
from scaffold.infra.prompts.loader import PromptLoader
from scaffold.infra.prompts.registry import PromptRegistry

__all__ = [
    "PromptAssembler",
    "PromptLoader",
    "PromptRegistry",
]
