"""提示词工程系统。

模板注册表、加载器和组装器，遵循 DeepAgents 提示词组装约定：
USER -> BASE -> CUSTOM -> SUFFIX。
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
