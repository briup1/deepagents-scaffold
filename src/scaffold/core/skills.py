"""技能系统。

加载 SKILL.md 定义文件，并为 SkillsMiddleware 提供技能发现能力。

改编自 deer-flow 的技能加载基础设施。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from scaffold.infra.config.app_config import AppConfig

logger = logging.getLogger(__name__)


def _scan_skill_directories(skills_path: str) -> list[Path]:
    """扫描技能目录中的 SKILL.md 文件。

    返回包含 SKILL.md 文件的目录列表。
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
    """返回可供加载的技能目录名称列表。

    这些名称将传给 DeepAgents 的 SkillsMiddleware。
    """
    path = app_config.skills.path
    # 展开环境变量与 ~
    path = os.path.expandvars(os.path.expanduser(path))
    dirs = _scan_skill_directories(path)
    return [d.name for d in dirs]


def load_skills(app_config: AppConfig) -> list[dict[str, Any]]:
    """加载所有 SKILL.md 文件并返回解析后的技能元数据。

    返回包含 'name'、'description'、'content' 键的字典列表。
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
    """解析 SKILL.md 文件中的 YAML frontmatter。

    期望格式：
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
