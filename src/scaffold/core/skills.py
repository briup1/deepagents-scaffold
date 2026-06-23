"""Skills system.

Loads SKILL.md definitions and provides skill discovery for the
SkillsMiddleware.

Adapted from deer-flow's skill loading infrastructure.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from scaffold.infra.config.app_config import AppConfig

logger = logging.getLogger(__name__)


def _scan_skill_directories(skills_path: str) -> list[Path]:
    """Scan the skills directory for SKILL.md files.

    Returns a list of directories that contain a SKILL.md file.
    """
    base = Path(skills_path)
    if not base.exists():
        return []

    skill_dirs: list[Path] = []
    for item in base.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            skill_dirs.append(item)
    return skill_dirs


def get_skill_names(app_config: AppConfig) -> list[str]:
    """Return the list of skill directory names available for loading.

    These names are passed to DeepAgents SkillsMiddleware.
    """
    path = app_config.skills.path
    # Expand env vars and ~
    path = os.path.expandvars(os.path.expanduser(path))
    dirs = _scan_skill_directories(path)
    return [d.name for d in dirs]


def load_skills(app_config: AppConfig) -> list[dict[str, Any]]:
    """Load all SKILL.md files and return parsed skill metadata.

    Returns a list of dicts with 'name', 'description', 'content' keys.
    """
    path = app_config.skills.path
    path = os.path.expandvars(os.path.expanduser(path))
    dirs = _scan_skill_directories(path)

    skills: list[dict[str, Any]] = []
    for skill_dir in dirs:
        skill_md = skill_dir / "SKILL.md"
        try:
            content = skill_md.read_text(encoding="utf-8")
            meta = _parse_skill_frontmatter(content)
            skills.append(
                {
                    "name": meta.get("name", skill_dir.name),
                    "description": meta.get("description", ""),
                    "content": content,
                }
            )
        except Exception:
            logger.exception("Failed to load skill from %s", skill_dir)

    return skills


def _parse_skill_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md file.

    Expects format:
        ---
        name: my-skill
        description: Does something useful
        ---
        # Markdown content...
    """
    import yaml

    meta: dict[str, Any] = {}
    if not content.startswith("---"):
        return meta

    parts = content.split("---", 2)
    if len(parts) >= 3:
        try:
            meta = yaml.safe_load(parts[1]) or {}
        except Exception:
            logger.debug("Failed to parse SKILL.md frontmatter")
    return meta
