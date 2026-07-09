"""结对代码审查员工具集。

提供文件读取、静态分析、测试运行、符号解释、patch 生成与安全写入能力。
"""

from __future__ import annotations

from pathlib import Path

import asyncio
import ast
import difflib
import os
import shutil
import sys

PROJECT_ROOT = Path(os.environ.get("SCAFFOLD_PROJECT_ROOT") or Path(__file__).resolve().parents[4])


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
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"错误：读取文件失败：{exc}"

    lines = content.splitlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + limit
    selected = lines[start:end]

    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(selected, start=start))


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

    def _list_entries() -> str:
        entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        return "\n".join(f"{'[DIR]' if entry.is_dir() else '[FILE]'} {entry.name}" for entry in entries)

    return await asyncio.to_thread(_list_entries)


async def run_ruff(relative_path: str) -> str:
    """对目标运行 ruff check。

    Args:
        relative_path: 相对于项目根目录的目标路径（文件或目录）。

    Returns:
        ruff 的退出码和输出。
    """
    path = _resolve_project_path(relative_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError:
        proc.kill()
        return "错误：运行 ruff 超时"
    except OSError as exc:
        return f"错误：无法运行 ruff：{exc}"
    return f"退出码：{proc.returncode}\n\n{stdout.decode(errors='replace')}\n{stderr.decode(errors='replace')}".strip()


async def run_pytest(relative_path: str) -> str:
    """对目标运行 pytest。

    Args:
        relative_path: 相对于项目根目录的测试目标。

    Returns:
        pytest 的退出码和输出。
    """
    path = _resolve_project_path(relative_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            str(path),
            "-v",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except TimeoutError:
        proc.kill()
        return "错误：运行 pytest 超时"
    except OSError as exc:
        return f"错误：无法运行 pytest：{exc}"
    return f"退出码：{proc.returncode}\n\n{stdout.decode(errors='replace')}\n{stderr.decode(errors='replace')}".strip()


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
        source = await asyncio.to_thread(path.read_text, encoding="utf-8")
        tree = await asyncio.to_thread(ast.parse, source)
    except SyntaxError as exc:
        return f"错误：语法错误：{exc}"
    except Exception as exc:  # noqa: BLE001
        return f"错误：解析失败：{exc}"

    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
            start = node.lineno - 1
            end = node.end_lineno
            snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            docstring = ast.get_docstring(node)
            doc = f"\n\n文档字符串：\n{docstring}" if docstring else ""
            return f"符号 `{symbol_name}` 定义：\n{snippet}{doc}"

    return f"未找到符号 `{symbol_name}`。"


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
    if not original_path.is_file():
        return f"错误：原始路径不是文件：{original_relative_path}"
    if not modified_path.exists():
        return f"错误：修改后文件不存在：{modified_relative_path}"
    if not modified_path.is_file():
        return f"错误：修改后路径不是文件：{modified_relative_path}"

    try:
        original_lines = (await asyncio.to_thread(original_path.read_text, encoding="utf-8")).splitlines()
        modified_lines = (await asyncio.to_thread(modified_path.read_text, encoding="utf-8")).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return f"错误：读取文件失败：{exc}"

    diff = await asyncio.to_thread(
        difflib.unified_diff,
        original_lines,
        modified_lines,
        fromfile=original_relative_path,
        tofile=modified_relative_path,
    )

    return "\n".join(diff)


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

    if path.is_dir():
        return f"错误：路径是目录，无法写入：{relative_path}"

    if path.exists() and not append:
        backup_path = path.with_suffix(path.suffix + ".bak")
        try:
            await asyncio.to_thread(shutil.copy2, path, backup_path)
        except OSError as exc:
            return f"错误：备份文件失败：{relative_path}，{exc}"

    try:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    except OSError as exc:
        return f"错误：创建目录失败：{path.parent}，{exc}"

    mode = "a" if append else "w"
    try:

        def _write() -> None:
            with path.open(mode=mode, encoding="utf-8") as handle:
                handle.write(content)

        await asyncio.to_thread(_write)
    except OSError as exc:
        return f"错误：写入文件失败：{relative_path}，{exc}"

    action = "追加到" if append else "写入"
    return f"成功{action}文件：{relative_path}"
