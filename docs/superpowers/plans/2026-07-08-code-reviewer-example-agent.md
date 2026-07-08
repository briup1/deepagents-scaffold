# 结对代码审查员示例 Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 DeepAgents 脚手架上新增一个可运行的“结对代码审查员”示例 Agent，包含 7 个工具、3 个子 Agent、1 个技能和示例项目，且不修改脚手架核心代码。

**Architecture:** 所有业务逻辑通过 `src/scaffold/plugins/` 中的工具函数与 `SKILL.md` 提供，通过 `config.yaml` 注册到脚手架。Agent 在现有 FastAPI/SSE 流式接口上运行，无需新增 API 或前端组件。

**Tech Stack:** Python 3.12, DeepAgents SDK, FastAPI, ruff, pytest, Pydantic, YAML

## Global Constraints

- 不得修改 `src/scaffold/core/`、`src/scaffold/infra/`、`src/scaffold/api/`、`src/scaffold/runtime/` 中的任何文件。
- 所有工具必须是异步可调用对象，且接受关键字参数。
- Python 函数必须带类型注解。
- 代码风格遵循 ruff：`line-length = 120`，`target-version = "py312"`。
- 所有文件路径基于项目根目录解析，禁止越界访问。
- `write_file` 禁止写入 `.env`、`config.yaml`、`.key/.secret/.pem/.p12` 文件以及 `core/infra/api/runtime/` 目录。
- 覆盖文件前自动创建 `.bak` 备份。
- 默认行为：Agent 生成 patch 后询问用户是否应用；用户明确说“直接改”时，可跳过确认。
- Agent 使用 Markdown 输出结构化审查报告。
- `config.yaml` 是唯一事实来源，热重载生效。
- `ruff` 必须在 `[project.optional-dependencies] dev` 中声明。

## File Structure Map

| 文件 | 职责 |
|---|---|
| `src/scaffold/plugins/tools/code_review.py` | 7 个代码审查工具：文件读取、目录列表、ruff、pytest、符号解释、生成 patch、安全写入 |
| `src/scaffold/plugins/skills/code_review/SKILL.md` | 审查清单、Markdown 输出模板、patch 应用规则 |
| `config.yaml` | 注册工具、子 Agent、画像，并设置 `default_harness: code_reviewer` |
| `pyproject.toml` | 在 `[project.optional-dependencies] dev` 中加入 `ruff` |
| `examples/code-reviewer/sample/bad_code.py` | 供 Agent 审查的示例问题代码 |
| `examples/code-reviewer/README.md` | 示例说明与运行方式 |
| `tests/plugins/test_code_review_tools.py` | 工具单元测试 |
| `tests/test_api.py` | 集成测试，验证 `/api/tools/` 返回新工具 |

---

### Task 1: 文件读取与目录列表工具

**Files:**
- Create: `src/scaffold/plugins/tools/code_review.py`
- Create: `tests/plugins/test_code_review_tools.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `PROJECT_ROOT: Path` — 项目根目录常量
  - `_resolve_project_path(relative_path: str) -> Path` — 解析并校验路径
  - `read_file(relative_path: str, offset: int = 1, limit: int | None = None) -> str`
  - `list_files(relative_path: str = ".") -> str`

- [ ] **Step 1: Write the failing tests**

在 `tests/plugins/test_code_review_tools.py` 中写入：

```python
"""结对代码审查员工具的单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from scaffold.plugins.tools.code_review import list_files, read_file


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.py"
    path.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    return path


def test_read_file_with_offset_and_limit(sample_file: Path, monkeypatch):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        sample_file.parent,
    )
    result = read_file(relative_path="sample.py", offset=2, limit=2)
    assert "2: line2" in result
    assert "3: line3" in result
    assert "1: line1" not in result
    assert "4: line4" not in result


def test_list_files(monkeypatch, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b_dir").mkdir()
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = list_files(relative_path=".")
    assert "[FILE] a.txt" in result
    assert "[DIR] b_dir" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_code_review_tools.py -v`

Expected: FAIL with `ImportError: cannot import name 'read_file' from 'scaffold.plugins.tools.code_review'` 或 `ModuleNotFoundError`。

- [ ] **Step 3: Write minimal implementation**

创建 `src/scaffold/plugins/tools/code_review.py`：

```python
"""结对代码审查员工具集。

提供文件读取、静态分析、测试运行、符号解释、patch 生成与安全写入能力。
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _resolve_project_path(relative_path: str) -> Path:
    """将相对路径解析为项目根目录下的绝对路径，并检查越界。

    Args:
        relative_path: 相对于项目根目录的路径。

    Returns:
        解析后的绝对路径。

    Raises:
        ValueError: 如果路径解析后超出项目根目录。
    """
    target = (PROJECT_ROOT / relative_path).resolve()
    if not target.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"路径超出项目根目录：{relative_path}")
    return target


async def read_file(relative_path: str, offset: int = 1, limit: int | None = None) -> str:
    """读取文件内容，支持行偏移和行数限制。

    Args:
        relative_path: 相对于项目根目录的文件路径。
        offset: 起始行号（1 开始）。
        limit: 最多读取行数，None 表示读取到末尾。

    Returns:
        带行号的文件内容，或错误信息。
    """
    path = _resolve_project_path(relative_path)
    if not path.exists():
        return f"错误：文件不存在：{relative_path}"
    if not path.is_file():
        return f"错误：路径不是文件：{relative_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"错误：读取文件失败：{exc}"

    lines = content.splitlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + limit
    selected = lines[start:end]

    return "\n".join(
        f"{i + 1}: {line}" for i, line in enumerate(selected, start=start)
    )


async def list_files(relative_path: str = ".") -> str:
    """列出目录中的文件和子目录。

    Args:
        relative_path: 相对于项目根目录的目录路径。

    Returns:
        文件和目录列表，或错误信息。
    """
    path = _resolve_project_path(relative_path)
    if not path.exists():
        return f"错误：路径不存在：{relative_path}"
    if not path.is_dir():
        return f"错误：路径不是目录：{relative_path}"

    entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    return "\n".join(
        f"{'[DIR]' if entry.is_dir() else '[FILE]'} {entry.name}"
        for entry in entries
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_code_review_tools.py -v`

Expected: `test_read_file_with_offset_and_limit` 和 `test_list_files` 通过。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add read_file and list_files tools"
```

---

### Task 2: ruff 静态分析工具

**Files:**
- Modify: `src/scaffold/plugins/tools/code_review.py`（在文件末尾添加 `run_ruff`）
- Modify: `tests/plugins/test_code_review_tools.py`（添加测试）

**Interfaces:**
- Consumes: `_resolve_project_path`
- Produces: `run_ruff(relative_path: str) -> str`

- [ ] **Step 1: Write the failing test**

在 `tests/plugins/test_code_review_tools.py` 中追加：

```python
from scaffold.plugins.tools.code_review import run_ruff


def test_run_ruff_reports_issues(monkeypatch, tmp_path: Path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import os\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = run_ruff(relative_path="bad.py")
    assert "F401" in result or "unused" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_code_review_tools.py::test_run_ruff_reports_issues -v`

Expected: FAIL with `ImportError: cannot import name 'run_ruff'`。

- [ ] **Step 3: Write minimal implementation**

在 `src/scaffold/plugins/tools/code_review.py` 顶部添加 `import asyncio`，并在文件末尾追加：

```python
async def run_ruff(relative_path: str) -> str:
    """对目标运行 ruff check。

    Args:
        relative_path: 相对于项目根目录的目标路径（文件或目录）。

    Returns:
        ruff 的退出码和输出。
    """
    path = _resolve_project_path(relative_path)
    proc = await asyncio.create_subprocess_exec(
        "ruff",
        "check",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return f"退出码：{proc.returncode}\n\n{stdout.decode()}\n{stderr.decode()}".strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_code_review_tools.py::test_run_ruff_reports_issues -v`

Expected: PASS（需确保 ruff 已安装；如未安装，先执行 `uv pip install -e ".[dev]"`）。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add run_ruff tool"
```

---

### Task 3: pytest 测试运行工具

**Files:**
- Modify: `src/scaffold/plugins/tools/code_review.py`（在文件末尾添加 `run_pytest`）
- Modify: `tests/plugins/test_code_review_tools.py`（添加测试）

**Interfaces:**
- Consumes: `_resolve_project_path`
- Produces: `run_pytest(relative_path: str) -> str`

- [ ] **Step 1: Write the failing test**

在 `tests/plugins/test_code_review_tools.py` 中追加：

```python
from scaffold.plugins.tools.code_review import run_pytest


def test_run_pytest_runs_tests(monkeypatch, tmp_path: Path):
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = run_pytest(relative_path="test_dummy.py")
    assert "passed" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_code_review_tools.py::test_run_pytest_runs_tests -v`

Expected: FAIL with `ImportError: cannot import name 'run_pytest'`。

- [ ] **Step 3: Write minimal implementation**

在 `src/scaffold/plugins/tools/code_review.py` 文件末尾追加：

```python
async def run_pytest(relative_path: str) -> str:
    """对目标运行 pytest。

    Args:
        relative_path: 相对于项目根目录的测试目标。

    Returns:
        pytest 的退出码和输出。
    """
    path = _resolve_project_path(relative_path)
    proc = await asyncio.create_subprocess_exec(
        "pytest",
        str(path),
        "-v",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return f"退出码：{proc.returncode}\n\n{stdout.decode()}\n{stderr.decode()}".strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_code_review_tools.py::test_run_pytest_runs_tests -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add run_pytest tool"
```

---

### Task 4: AST 符号解释工具

**Files:**
- Modify: `src/scaffold/plugins/tools/code_review.py`（在文件末尾添加 `explain_symbol`）
- Modify: `tests/plugins/test_code_review_tools.py`（添加测试）

**Interfaces:**
- Consumes: `_resolve_project_path`
- Produces: `explain_symbol(relative_path: str, symbol_name: str) -> str`

- [ ] **Step 1: Write the failing test**

在 `tests/plugins/test_code_review_tools.py` 中追加：

```python
from scaffold.plugins.tools.code_review import explain_symbol


def test_explain_symbol_finds_function(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "module.py"
    source_file.write_text(
        'def add(a: int, b: int) -> int:\n    """Return sum."""\n    return a + b\n'
        "\n"
        "class Box:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = explain_symbol(relative_path="module.py", symbol_name="add")
    assert "def add" in result
    assert "Return sum" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_code_review_tools.py::test_explain_symbol_finds_function -v`

Expected: FAIL with `ImportError: cannot import name 'explain_symbol'`。

- [ ] **Step 3: Write minimal implementation**

在 `src/scaffold/plugins/tools/code_review.py` 顶部添加 `import ast`，并在文件末尾追加：

```python
async def explain_symbol(relative_path: str, symbol_name: str) -> str:
    """解析 AST，解释函数或类定义。

    Args:
        relative_path: 相对于项目根目录的文件路径。
        symbol_name: 要查找的函数或类名称。

    Returns:
        符号定义片段和文档字符串，或错误信息。
    """
    path = _resolve_project_path(relative_path)
    if not path.exists():
        return f"错误：文件不存在：{relative_path}"
    if not path.is_file():
        return f"错误：路径不是文件：{relative_path}"

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"错误：语法错误：{exc}"
    except Exception as exc:  # noqa: BLE001
        return f"错误：解析失败：{exc}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
            lines = source.splitlines()
            start = node.lineno - 1
            end = node.end_lineno
            snippet = "\n".join(
                f"{i + 1}: {lines[i]}" for i in range(start, end)
            )
            docstring = ast.get_docstring(node)
            doc = f"\n\n文档字符串：\n{docstring}" if docstring else ""
            return f"符号 `{symbol_name}` 定义：\n{snippet}{doc}"

    return f"未找到符号 `{symbol_name}`。"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_code_review_tools.py::test_explain_symbol_finds_function -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add explain_symbol tool"
```

---

### Task 5: Patch 生成工具

**Files:**
- Modify: `src/scaffold/plugins/tools/code_review.py`（在文件末尾添加 `generate_patch`）
- Modify: `tests/plugins/test_code_review_tools.py`（添加测试）

**Interfaces:**
- Consumes: `_resolve_project_path`
- Produces: `generate_patch(original_relative_path: str, modified_relative_path: str) -> str`

- [ ] **Step 1: Write the failing test**

在 `tests/plugins/test_code_review_tools.py` 中追加：

```python
from scaffold.plugins.tools.code_review import generate_patch


def test_generate_patch(monkeypatch, tmp_path: Path):
    original = tmp_path / "original.py"
    original.write_text("def foo():\n    return 1\n", encoding="utf-8")
    modified = tmp_path / "modified.py"
    modified.write_text("def foo():\n    return 2\n", encoding="utf-8")
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = generate_patch(
        original_relative_path="original.py",
        modified_relative_path="modified.py",
    )
    assert "--- original.py" in result
    assert "+++ modified.py" in result
    assert "-    return 1" in result
    assert "+    return 2" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_code_review_tools.py::test_generate_patch -v`

Expected: FAIL with `ImportError: cannot import name 'generate_patch'`。

- [ ] **Step 3: Write minimal implementation**

在 `src/scaffold/plugins/tools/code_review.py` 顶部添加 `import difflib`，并在文件末尾追加：

```python
async def generate_patch(original_relative_path: str, modified_relative_path: str) -> str:
    """生成两个文件之间的统一 diff。

    Args:
        original_relative_path: 原始文件路径。
        modified_relative_path: 修改后的文件路径。

    Returns:
        unified diff 字符串，或错误信息。
    """
    original_path = _resolve_project_path(original_relative_path)
    modified_path = _resolve_project_path(modified_relative_path)

    if not original_path.exists():
        return f"错误：原始文件不存在：{original_relative_path}"
    if not modified_path.exists():
        return f"错误：修改后文件不存在：{modified_relative_path}"

    original_lines = original_path.read_text(encoding="utf-8").splitlines()
    modified_lines = modified_path.read_text(encoding="utf-8").splitlines()

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=original_relative_path,
        tofile=modified_relative_path,
    )
    return "\n".join(diff)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_code_review_tools.py::test_generate_patch -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add generate_patch tool"
```

---

### Task 6: 安全写入工具

**Files:**
- Modify: `src/scaffold/plugins/tools/code_review.py`（添加安全校验与 `write_file`）
- Modify: `tests/plugins/test_code_review_tools.py`（添加测试）

**Interfaces:**
- Consumes: `_resolve_project_path`, `PROJECT_ROOT`
- Produces:
  - `_validate_write_path(path: Path) -> None`
  - `write_file(relative_path: str, content: str, append: bool = False) -> str`

- [ ] **Step 1: Write the failing tests**

在 `tests/plugins/test_code_review_tools.py` 中追加：

```python
from scaffold.plugins.tools.code_review import write_file


def test_write_file_allowed_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = write_file(relative_path="allowed.txt", content="hello")
    assert "成功写入" in result
    assert (tmp_path / "allowed.txt").read_text(encoding="utf-8") == "hello"


def test_write_file_forbidden_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    result = write_file(relative_path=".env", content="secret")
    assert "禁止写入" in result
    assert not (tmp_path / ".env").exists()


def test_write_file_creates_backup(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "scaffold.plugins.tools.code_review.PROJECT_ROOT",
        tmp_path,
    )
    target = tmp_path / "existing.txt"
    target.write_text("old", encoding="utf-8")
    result = write_file(relative_path="existing.txt", content="new")
    assert "成功写入" in result
    assert target.read_text(encoding="utf-8") == "new"
    assert (tmp_path / "existing.txt.bak").read_text(encoding="utf-8") == "old"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/plugins/test_code_review_tools.py -k write_file -v`

Expected: FAIL with `ImportError: cannot import name 'write_file'`。

- [ ] **Step 3: Write minimal implementation**

在 `src/scaffold/plugins/tools/code_review.py` 顶部添加 `import shutil`，并在 `_resolve_project_path` 之后、`read_file` 之前插入以下常量与辅助函数：

```python
_FORBIDDEN_FILES = {".env", "config.yaml"}
_FORBIDDEN_SUFFIXES = {".key", ".secret", ".pem", ".p12"}
_PROTECTED_DIRS = {"core", "infra", "api", "runtime"}


def _validate_write_path(path: Path) -> None:
    """检查路径是否允许写入。

    Args:
        path: 目标文件路径。

    Raises:
        ValueError: 如果路径命中禁止规则或越界。
    """
    if path.name in _FORBIDDEN_FILES:
        raise ValueError(f"禁止写入文件：{path.name}")
    if path.suffix in _FORBIDDEN_SUFFIXES:
        raise ValueError(f"禁止写入后缀为 {path.suffix} 的文件")

    resolved = path.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("路径超出项目根目录")

    rel_parts = resolved.relative_to(PROJECT_ROOT).parts
    if len(rel_parts) >= 3 and rel_parts[0] == "src" and rel_parts[1] == "scaffold":
        if rel_parts[2] in _PROTECTED_DIRS:
            raise ValueError(f"禁止写入到 src/scaffold/{rel_parts[2]}/")
```

在文件末尾追加：

```python
async def write_file(relative_path: str, content: str, append: bool = False) -> str:
    """写入或追加文件，自动备份并带安全限制。

    Args:
        relative_path: 相对于项目根目录的文件路径。
        content: 要写入的内容。
        append: 为 True 时追加，否则覆盖。

    Returns:
        操作结果描述，或错误信息。
    """
    path = _resolve_project_path(relative_path)

    try:
        _validate_write_path(path)
    except ValueError as exc:
        return f"错误：{exc}"

    if path.exists() and not append:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode=mode, encoding="utf-8") as handle:
        handle.write(content)

    action = "追加到" if append else "写入"
    return f"成功{action}文件：{relative_path}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/plugins/test_code_review_tools.py -k write_file -v`

Expected: 三个测试全部通过。

- [ ] **Step 5: Commit**

```bash
git add src/scaffold/plugins/tools/code_review.py tests/plugins/test_code_review_tools.py
git commit -m "feat(code-reviewer): add write_file with safety restrictions"
```

---

### Task 7: 代码审查 SKILL.md

**Files:**
- Create: `src/scaffold/plugins/skills/code_review/SKILL.md`

**Interfaces:**
- Consumes: 无
- Produces: 技能文档，由 `SkillsMiddleware` 自动加载到 Agent 上下文

- [ ] **Step 1: Write the SKILL.md**

创建 `src/scaffold/plugins/skills/code_review/SKILL.md`：

```markdown
---
name: code_review
description: 结对代码审查员审查清单与输出模板
---

# 结对代码审查员技能

## 审查清单

审查代码时，请检查以下方面：

1. **命名**：变量、函数、类名是否清晰、一致？
2. **类型注解**：函数参数和返回值是否有类型注解？
3. **异常处理**：是否捕获了具体异常，而不是裸 `except`？
4. **文档**：模块、函数、类是否有合适的 docstring？
5. **测试**：是否有覆盖关键路径的单元测试？
6. **复杂度**：函数是否过长，职责是否单一？
7. **可维护性**：是否有重复代码、魔法数字、过深嵌套？

## 输出模板

使用以下 Markdown 模板输出审查报告：

```markdown
# 代码审查报告：`<file_path>`

## 摘要
- 审查文件数：
- 发现问题数：
- 严重程度：

## 详细发现

### 1. `<问题类别>`：`<问题描述>`
- 位置：`<文件路径>:<行号>`
- 建议：`<具体修改建议>`
- 严重程度：高/中/低

## 行动计划

1. 生成 patch
2. 向用户展示 patch
3. 用户确认后，使用 write_file 应用修改
```

## Patch 应用规则

- 默认情况下，先生成 patch 并询问用户是否应用。
- 如果用户明确说“直接改”、“应用 patch”或类似表达，可以跳过确认。
- 覆盖文件前，`write_file` 会自动创建 `.bak` 备份。
- 禁止写入 `.env`、`config.yaml`、密钥文件以及 `core/infra/api/runtime/` 目录。

## 子 Agent 使用指南

- `reviewer`：用于检查 bug、风格和可维护性。
- `tester`：用于生成并运行测试。
- `refactorer`：用于提出重构并生成 patch。
- 主 Agent 负责整合三方结果，输出 Markdown 报告并与用户确认修改。
```

- [ ] **Step 2: Verify skill loading**

Run: `python -c "from scaffold.core.skills import get_skill_names; from scaffold.infra.config.app_config import get_app_config; print(get_skill_names(get_app_config()))"`

Expected: 输出包含 `code_review`。

- [ ] **Step 3: Commit**

```bash
git add src/scaffold/plugins/skills/code_review/SKILL.md
git commit -m "feat(code-reviewer): add code review skill"
```

---

### Task 8: 注册工具、子 Agent 与画像

**Files:**
- Modify: `config.yaml`

**Interfaces:**
- Consumes: 工具实现 `scaffold.plugins.tools.code_review:*`、技能 `code_review`
- Produces: 配置变更，使 `default_harness: code_reviewer` 生效

- [ ] **Step 1: Update skills path**

在 `config.yaml` 第 65-68 行的 `skills` 配置处替换为：

```yaml
skills:
  path: src/scaffold/plugins/skills
  container_path: /mnt/skills
```

- [ ] **Step 2: Add tool definitions**

在 `config.yaml` 第 55 行的 `tools: []` 处替换为：

```yaml
tools:
  - name: read_file
    use: scaffold.plugins.tools.code_review:read_file
  - name: list_files
    use: scaffold.plugins.tools.code_review:list_files
  - name: run_ruff
    use: scaffold.plugins.tools.code_review:run_ruff
  - name: run_pytest
    use: scaffold.plugins.tools.code_review:run_pytest
  - name: explain_symbol
    use: scaffold.plugins.tools.code_review:explain_symbol
  - name: generate_patch
    use: scaffold.plugins.tools.code_review:generate_patch
  - name: write_file
    use: scaffold.plugins.tools.code_review:write_file
```

- [ ] **Step 3: Add subagent definitions**

在 `config.yaml` 第 199-211 行的 `subagent_definitions.items` 末尾追加：

```yaml
    - name: reviewer
      description: "检查 bug、风格和可维护性"
      system_prompt: "你是一名严格的代码审查员。仔细阅读代码，检查 bug、风格、类型注解、异常处理、文档、测试覆盖和可维护性。用 Markdown 输出发现清单，每条包含位置、描述和建议。"
      tools: ["read_file", "list_files", "run_ruff", "explain_symbol"]
      enabled: true
    - name: tester
      description: "生成并运行测试"
      system_prompt: "你是一名测试工程师。阅读代码后，为关键路径编写 pytest 单元测试，写入 tests/ 目录，然后运行测试并报告结果。"
      tools: ["read_file", "run_pytest", "write_file"]
      enabled: true
    - name: refactorer
      description: "提出并应用重构建议"
      system_prompt: "你是一名重构专家。根据审查意见，编写修改后的文件版本，使用 generate_patch 生成统一 diff，并在用户确认后使用 write_file 应用修改。"
      tools: ["read_file", "explain_symbol", "generate_patch", "write_file"]
      enabled: true
```

- [ ] **Step 4: Add harness profile**

在 `config.yaml` 第 148-160 行的 `profiles.harness` 列表末尾追加，并修改 `default_harness`：

```yaml
    - name: code_reviewer
      base_system_prompt: "你是一名结对代码审查员。你的目标是通过读取代码、运行静态分析和测试、委派子 Agent，帮助用户发现质量问题并生成改进方案。"
      system_prompt_suffix: "请使用 Markdown 输出结构化的审查报告。在应用 patch 前，默认先询问用户确认；如果用户明确说'直接改'或'应用 patch'，则可以跳过确认。禁止写入 .env、config.yaml、密钥文件以及 core/infra/api/runtime/ 目录。"
      excluded_middleware: []
      excluded_tools: []
  default_harness: code_reviewer
```

- [ ] **Step 5: Verify configuration**

Run: `python -c "from scaffold.infra.config.app_config import get_app_config; cfg = get_app_config(); print([t.name for t in cfg.tools]); print([s.name for s in cfg.subagent_definitions.get_enabled()]); print(cfg.profiles.default_harness); print(cfg.skills.path)"`

Expected: 输出包含全部 7 个工具名、`reviewer`、`tester`、`refactorer`、`code_reviewer` 和 `src/scaffold/plugins/skills`。

- [ ] **Step 6: Commit**

```bash
git add config.yaml
git commit -m "feat(code-reviewer): register tools, subagents, harness and skills path"
```

---

### Task 9: 声明 ruff 开发依赖

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 无
- Produces: `[project.optional-dependencies] dev` 包含 `ruff`

- [ ] **Step 1: Modify pyproject.toml**

在 `pyproject.toml` 第 29-33 行的 `dev` 依赖列表中添加 `ruff`：

```toml
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.28.0",
    "ruff>=0.15.20",
]
```

- [ ] **Step 2: Install and verify**

Run: `uv pip install -e ".[dev]" && ruff --version`

Expected: 安装成功，且 `ruff --version` 返回版本号。

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add ruff to dev optional dependencies"
```

---

### Task 10: 示例问题代码

**Files:**
- Create: `examples/code-reviewer/sample/bad_code.py`

**Interfaces:**
- Consumes: 无
- Produces: 可被 Agent 审查的示例文件

- [ ] **Step 1: Create sample file**

创建 `examples/code-reviewer/sample/bad_code.py`：

```python
import os
import sys


def calc(a, b):
    try:
        result = a / b
    except:
        result = None
    return result


class DataProcessor:
    def process(self, data):
        x = 0
        for item in data:
            if item % 2 == 0:
                x += item * 2
            else:
                x -= item
        return x


def very_long_function_name_that_does_little_to_nothing_really_and_should_be_refactored():
    pass
```

- [ ] **Step 2: Commit**

```bash
git add examples/code-reviewer/sample/bad_code.py
git commit -m "feat(code-reviewer): add sample bad code for review"
```

---

### Task 11: API 集成测试

**Files:**
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `config.yaml` 中已注册的工具
- Produces: 验证 `/api/tools/` 返回新工具的测试

- [ ] **Step 1: Write the failing test**

在 `tests/test_api.py` 文件末尾追加：

```python

def test_code_review_tools_listed(client):
    response = client.get("/api/tools/")
    assert response.status_code == 200
    data = response.json()
    names = {t["name"] for t in data["tools"]}
    expected = {
        "read_file",
        "list_files",
        "run_ruff",
        "run_pytest",
        "explain_symbol",
        "generate_patch",
        "write_file",
    }
    assert expected.issubset(names)
```

- [ ] **Step 2: Run test to verify it fails before config update**

Run: `pytest tests/test_api.py::test_code_review_tools_listed -v`

Expected: 若 `config.yaml` 尚未更新，则 FAIL with assertion error；若已更新，则 PASS。

- [ ] **Step 3: Ensure it passes after config update**

Run: `pytest tests/test_api.py::test_code_review_tools_listed -v`

Expected: PASS（依赖 Task 8 的 `config.yaml` 变更）。

- [ ] **Step 4: Commit**

```bash
git add tests/test_api.py
git commit -m "test(api): verify code review tools are exposed"
```

---

### Task 12: 示例 README

**Files:**
- Create: `examples/code-reviewer/README.md`

**Interfaces:**
- Consumes: 无
- Produces: 示例文档

- [ ] **Step 1: Write README**

创建 `examples/code-reviewer/README.md`：

```markdown
# 结对代码审查员示例

本示例展示如何在 DeepAgents 脚手架上组装一个“结对代码审查员”Agent。

## 包含内容

- `sample/bad_code.py`：一段带有常见问题的示例代码。
- `src/scaffold/plugins/tools/code_review.py`：7 个代码审查工具。
- `src/scaffold/plugins/skills/code_review/SKILL.md`：审查清单与输出模板。
- `config.yaml`：工具、子 Agent 与画像配置。

## 快速体验

1. 确保依赖已安装：

   ```bash
   uv pip install -e ".[dev]"
   ```

2. 启动后端和前端：

   ```bash
   bash scripts/dev.sh
   ```

3. 打开前端页面 `http://localhost:3000`，输入：

   ```
   请审查 examples/code-reviewer/sample/bad_code.py
   ```

4. 观察 Agent 读取文件、运行 `ruff`、调用 `reviewer` 子 Agent，并输出 Markdown 审查报告。

## 应用 Patch

Agent 生成 patch 后，默认会询问你是否应用。你可以回复：

- “应用 patch”或“直接改”——Agent 会写入文件并自动创建 `.bak` 备份。
- “再想想”或“不要应用”——Agent 仅保留报告，不修改文件。

## 安全限制

`write_file` 工具禁止写入：

- `.env`、`config.yaml`
- 后缀为 `.key`、`.secret`、`.pem`、`.p12` 的文件
- `src/scaffold/core/`、`src/scaffold/infra/`、`src/scaffold/api/`、`src/scaffold/runtime/`
```

- [ ] **Step 2: Commit**

```bash
git add examples/code-reviewer/README.md
git commit -m "docs(code-reviewer): add example README"
```

---

## 最终验证

所有任务完成后，按顺序运行以下命令：

```bash
ruff check src tests
ruff format src tests
pytest
bash scripts/dev.sh
```

手动验证：

- 后端健康检查：`curl -s http://localhost:8000/health`
- 工具列表：`curl -s http://localhost:8000/api/tools/ | grep code_review`
- 流式审查：`curl -N -X POST http://localhost:8000/api/runs/stream -H "Content-Type: application/json" -d '{"agent_id":"code_reviewer","message":"请审查 examples/code-reviewer/sample/bad_code.py"}'`

---

## Self-Review

1. **Spec coverage:**
   - 7 个工具：Task 1-6 覆盖。
   - 3 个子 Agent：Task 8 覆盖。
   - `code_reviewer` 画像与 `default_harness`：Task 8 覆盖。
   - SKILL.md 与 `skills.path` 指向 `src/scaffold/plugins/skills`：Task 7-8 覆盖。
   - 安全限制与备份：Task 6 覆盖。
   - 示例代码与 README：Task 10、12 覆盖。
   - 测试：Task 1-6、11 覆盖。
   - `pyproject.toml` 加 `ruff`：Task 9 覆盖。
   - 未修改 `core/infra/api/runtime`：Global Constraints 明确禁止。

2. **Placeholder scan:** 本计划无 TBD/TODO/“稍后实现”/“适当处理”等占位符。每个步骤包含完整代码、命令和预期结果。

3. **Type consistency:**
   - `read_file` 签名统一为 `relative_path: str, offset: int = 1, limit: int | None = None -> str`。
   - `list_files` 签名为 `relative_path: str = "." -> str`。
   - `write_file` 签名为 `relative_path: str, content: str, append: bool = False -> str`。
   - `config.yaml` 中注册路径与代码实现一致：`scaffold.plugins.tools.code_review:<function_name>`。
   - 子 Agent 工具白名单中的工具名与 `config.yaml` 中定义的工具名一致。

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-08-code-reviewer-example-agent.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
