"""skill 隔离与 allowed-tools 启动校验的测试。"""

from pathlib import Path

import pytest

from scaffold.core.skills import get_skill_names, parse_allowed_tools, validate_skill_tools
from scaffold.infra.config.app_config import AppConfig, SkillsConfig
from scaffold.infra.config.profile_config import HarnessProfileConfig


def _make_skill(base: Path, name: str, allowed_tools: str | None = None) -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    fm = f"---\nname: {name}\ndescription: test\n"
    if allowed_tools is not None:
        fm += f"allowed-tools: {allowed_tools}\n"
    (skill_dir / "SKILL.md").write_text(fm + "---\n\nbody\n", encoding="utf-8")
    return skill_dir


class TestParseAllowedTools:
    def test_empty(self):
        assert parse_allowed_tools("---\nname: x\n---\n") == set()
        assert parse_allowed_tools("no frontmatter") == set()

    def test_space_separated(self):
        content = "---\nallowed-tools: read_file run_pytest\n---\n"
        assert parse_allowed_tools(content) == {"read_file", "run_pytest"}

    def test_arg_syntax_takes_bare_name(self):
        content = "---\nallowed-tools: Bash(git:*) Read\n---\n"
        assert parse_allowed_tools(content) == {"Bash", "Read"}


class TestGetSkillNames:
    def test_global_path_str(self, tmp_path):
        _make_skill(tmp_path, "s1")
        cfg = AppConfig(skills=SkillsConfig(path=str(tmp_path)))
        assert get_skill_names(cfg) == [str(tmp_path.resolve())]

    def test_profile_inherits_global(self, tmp_path):
        _make_skill(tmp_path, "s1")
        cfg = AppConfig(skills=SkillsConfig(path=[str(tmp_path)]))
        profile = HarnessProfileConfig(name="p")  # skills=None → 继承
        assert get_skill_names(cfg, profile) == [str(tmp_path.resolve())]

    def test_profile_empty_means_no_skills(self, tmp_path):
        _make_skill(tmp_path, "s1")
        cfg = AppConfig(skills=SkillsConfig(path=[str(tmp_path)]))
        profile = HarnessProfileConfig(name="p", skills=[])
        assert get_skill_names(cfg, profile) == []

    def test_profile_whitelist(self, tmp_path):
        extraction = tmp_path / "extraction"
        review = tmp_path / "review"
        _make_skill(extraction, "extraction-goal")
        _make_skill(review, "code-review")
        cfg = AppConfig(skills=SkillsConfig(path=[str(extraction), str(review)]))
        profile = HarnessProfileConfig(name="p", skills=[str(review)])
        assert get_skill_names(cfg, profile) == [str(review.resolve())]


class TestValidateSkillTools:
    def test_pass_when_tools_available(self, tmp_path):
        _make_skill(tmp_path, "s1", "read_file run_pytest")
        assert validate_skill_tools([str(tmp_path)], {"read_file", "run_pytest", "write_file"}) == []

    def test_fail_when_tool_missing(self, tmp_path):
        _make_skill(tmp_path, "s1", "read_file run_pytest")
        errors = validate_skill_tools([str(tmp_path)], {"read_file"})
        assert len(errors) == 1
        assert "run_pytest" in errors[0]

    def test_undeclared_skill_skipped(self, tmp_path):
        _make_skill(tmp_path, "s1")  # 无 allowed-tools
        assert validate_skill_tools([str(tmp_path)], set()) == []

    def test_empty_sources(self):
        assert validate_skill_tools([], set()) == []


def test_real_plugins_skills_are_valid():
    """仓库内置 skill 的 allowed-tools 声明与工具注册表一致（冒烟）。"""
    from scaffold.core.tools import get_available_tools
    from scaffold.infra.config.app_config import get_app_config

    cfg = get_app_config()
    available = {t.name for t in get_available_tools(cfg)}
    errors = validate_skill_tools(get_skill_names(cfg), available)
    assert errors == [], errors


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
