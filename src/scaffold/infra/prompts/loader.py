"""提示词模板加载器。

从文件系统加载 .md 模板文件。
"""

from __future__ import annotations

import logging
from pathlib import Path

from scaffold.infra.prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptLoader:
    """从磁盘加载 Markdown 格式的提示词模板。"""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else DEFAULT_TEMPLATE_DIR

    def load_all(self, registry: PromptRegistry | None = None) -> PromptRegistry:
        """从目录加载所有 .md 文件到注册表中。

        文件名（不含 .md）作为模板名称。
        """
        if registry is None:
            registry = PromptRegistry()

        if not self.directory.exists():
            logger.debug("Template directory not found: %s", self.directory)
            return registry

        for md_file in self.directory.glob("*.md"):
            name = md_file.stem
            try:
                content = md_file.read_text(encoding="utf-8")
                registry.register(name, content)
                logger.debug("Loaded prompt template: %s", name)
            except Exception:
                logger.exception("Failed to load prompt template: %s", md_file)

        return registry
