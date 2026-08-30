"""技能系统。

加载 SKILL.md 定义文件，并为 SkillsMiddleware 提供技能发现能力。

改编自 deer-flow 的技能加载基础设施。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from scaffold.infra.config.app_config import AppConfig
from scaffold.infra.config.profile_config import HarnessProfileConfig

logger = logging.getLogger(__name__)


def _skill_source_paths(app_config: AppConfig, profile: HarnessProfileConfig | None = None) -> list[str]:
    """解析 skill source 目录列表。

    三态：profile.skills 为 None → 继承全局 skills.path；[] → 空；列表 → 域目录白名单。
    """
    if profile is not None and profile.skills is not None:
        raw: str | list[str] = profile.skills
    else:
        raw = app_config.skills.path
    paths = [raw] if isinstance(raw, str) else list(raw)
    return [os.path.expandvars(os.path.expanduser(p)) for p in paths]


def _scan_skill_directories(skills_path: str) -> list[Path]:
    """扫描技能目录中的 SKILL.md 文件。

    返回包含 SKILL.md 文件的目录列表（绝对路径）。
    """
    base = Path(skills_path).resolve()
    if not base.exists():
        return []

    skill_dirs: list[Path] = []
    for item in base.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            skill_dirs.append(item)
    return skill_dirs


def get_skill_names(app_config: AppConfig, profile: HarnessProfileConfig | None = None) -> list[str]:
    """返回 DeepAgents SkillsMiddleware 的 source 路径列表。

    SkillsMiddleware 期望 source 是包含 skill 子目录的父目录，
    它会自行扫描子目录下的 SKILL.md 文件。
    """
    sources: list[str] = []
    for path in _skill_source_paths(app_config, profile):
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            continue
        # 只有在存在 skill 子目录时才返回 source，避免空目录触发无意义加载
        if _scan_skill_directories(str(resolved)):
            sources.append(str(resolved))
    return sources


def parse_allowed_tools(content: str) -> set[str]:
    """解析 SKILL.md frontmatter 中的 allowed-tools 声明。

    规范定义为空格分隔字符串，兼容 `Bash(git:*)` 参数语法（取括号前的裸工具名）。
    """
    raw = _parse_skill_frontmatter(content).get("allowed-tools") or ""
    return {tok.split("(")[0] for tok in str(raw).split() if tok}


def validate_skill_tools(sources: list[str], available: set[str]) -> list[str]:
    """校验各 source 下 skill 声明的 allowed-tools 是否都在可用工具集中。

    返回错误描述列表；空列表表示全部通过。未声明 allowed-tools 的 skill 跳过。
    """
    errors: list[str] = []
    for source in sources:
        for skill_dir in _scan_skill_directories(source):
            required = parse_allowed_tools((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
            missing = sorted(required - available)
            if missing:
                errors.append(f"skill '{skill_dir.name}' 缺少工具: {missing}")
    return errors


def load_skills(app_config: AppConfig) -> list[dict[str, Any]]:
    """加载所有 SKILL.md 文件并返回解析后的技能元数据。

    返回包含 'name'、'description'、'content' 键的字典列表。
    """
    skills: list[dict[str, Any]] = []
    for path in _skill_source_paths(app_config):
        for skill_dir in _scan_skill_directories(path):
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
