"""提示词组装器。

按照 DeepAgents 约定组装系统提示词：
USER -> BASE -> CUSTOM -> SUFFIX。

与 deepagents.graph 中记录的组装顺序一致。
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from scaffold.infra.prompts.loader import PromptLoader
from scaffold.infra.prompts.registry import PromptRegistry


class PromptAssembler:
    """从模板片段组装系统提示词。"""

    def __init__(self) -> None:
        self.registry = PromptRegistry()
        self._loaded = False

    def load_defaults(self) -> None:
        """从 templates 目录加载默认模板。"""
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
        """组装提示词字符串。

        Args:
            user: USER 片段（前置，调用者指令）。
            base: BASE 片段（默认行为）。
            custom: CUSTOM 片段（若提供则替换 BASE）。
            suffix: SUFFIX 片段（最后追加，模型调优）。

        Returns:
            组装后的提示词文本。
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
        """从片段组装 SystemMessage。"""
        text = self.assemble(user=user, base=base, custom=custom, suffix=suffix)
        return SystemMessage(content=text)
