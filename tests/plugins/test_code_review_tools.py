"""结对代码审查员工具的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from scaffold.plugins.tools.code_review import list_files, read_file, run_ruff


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.py"
    path.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    return path


async def test_read_file_with_offset_and_limit(sample_file: Path, monkeypatch):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        sample_file.parent,
    )
    result = await read_file(relative_path="sample.py", offset=2, limit=2)
    assert "2: line2" in result
    assert "3: line3" in result
    assert "1: line1" not in result
    assert "4: line4" not in result


async def test_list_files(monkeypatch, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b_dir").mkdir()
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await list_files(relative_path=".")
    assert "[FILE] a.txt" in result
    assert "[DIR] b_dir" in result


async def test_run_ruff_reports_issues(monkeypatch, tmp_path: Path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import os\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await run_ruff(relative_path="bad.py")
    assert "F401" in result or "unused" in result.lower()
