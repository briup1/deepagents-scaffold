"""结对代码审查员工具的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from scaffold.plugins.tools.code_review import (
    explain_symbol,
    generate_patch,
    list_files,
    read_file,
    run_pytest,
    run_ruff,
    write_file,
)


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


async def test_explain_symbol_finds_function(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "module.py"
    source_file.write_text(
        'def add(a: int, b: int) -> int:\n    """Return sum."""\n    return a + b\n\nclass Box:\n    pass\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await explain_symbol(relative_path="module.py", symbol_name="add")
    assert "def add" in result
    assert "Return sum" in result


async def test_run_pytest_runs_tests(monkeypatch, tmp_path: Path):
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await run_pytest(relative_path="test_dummy.py")
    assert "passed" in result.lower()


async def test_generate_patch(monkeypatch, tmp_path: Path):
    original = tmp_path / "original.py"
    original.write_text("def foo():\n    return 1\n", encoding="utf-8")
    modified = tmp_path / "modified.py"
    modified.write_text("def foo():\n    return 2\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await generate_patch(
        original_relative_path="original.py",
        modified_relative_path="modified.py",
    )
    assert "--- original.py" in result
    assert "+++ modified.py" in result
    assert "-    return 1" in result
    assert "+    return 2" in result


async def test_write_file_allowed_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await write_file(relative_path="allowed.txt", content="hello")
    assert "成功写入" in result
    assert (tmp_path / "allowed.txt").read_text(encoding="utf-8") == "hello"


async def test_write_file_forbidden_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = await write_file(relative_path=".env", content="secret")
    assert "禁止写入" in result
    assert not (tmp_path / ".env").exists()


async def test_write_file_creates_backup(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    result = await write_file(relative_path="existing.txt", content="new")
    assert "成功写入" in result
    assert target.read_text(encoding="utf-8") == "new"
    assert (tmp_path / "existing.txt.bak").read_text(encoding="utf-8") == "old"
