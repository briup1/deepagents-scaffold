"""Prompt template loader.

Loads .md template files from the filesystem.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scaffold.infra.prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptLoader:
    """Load prompt templates from Markdown files on disk."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else DEFAULT_TEMPLATE_DIR

    def load_all(self, registry: PromptRegistry | None = None) -> PromptRegistry:
        """Load all .md files from the directory into a registry.

        File names (without .md) become template names.
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
