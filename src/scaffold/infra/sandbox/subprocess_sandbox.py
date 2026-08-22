"""基于受限子进程的 MVP 沙箱实现。"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from scaffold.infra.sandbox.base import Sandbox, SandboxResult

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_IMPORTS: set[str] = {
    "__future__",
    "os",
    "sys",
    "time",
    "pandas",
    "openpyxl",
    "numpy",
    "csv",
    "json",
    "re",
    "math",
    "datetime",
    "typing",
    "collections",
    "itertools",
    "statistics",
    "string",
    "hashlib",
    "base64",
    "decimal",
    "fractions",
    "numbers",
}

FORBIDDEN_FUNCTIONS: set[tuple[str | None, str]] = {
    (None, "__import__"),
    (None, "eval"),
    (None, "exec"),
    (None, "compile"),
    ("os", "system"),
    ("os", "popen"),
    ("os", "exec"),
    ("os", "spawn"),
    ("subprocess", "call"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("socket", "socket"),
    ("socket", "create_connection"),
    ("urllib", "urlopen"),
    ("urllib", "request"),
}


class SubprocessSandbox(Sandbox):
    """受限子进程沙箱。

    当前实现通过 AST 静态扫描限制导入与危险调用，并通过子进程超时控制。
    注意：这是 MVP 方案，生产环境应替换为 E2B / Docker / Firecracker 等专业沙箱。
    """

    def __init__(
        self,
        python_executable: str | None = None,
        allowed_imports: set[str] | None = None,
    ) -> None:
        self._python = python_executable or sys.executable
        self._allowed_imports = allowed_imports or DEFAULT_ALLOWED_IMPORTS

    def _validate_script(self, script_path: Path) -> None:
        """对脚本进行 AST 级别的安全检查。"""
        try:
            source = script_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ValueError(f"脚本语法错误：{exc}") from exc

        for node in ast.walk(tree):
            self._check_node(node)

    def _check_node(self, node: ast.AST) -> None:
        """检查单个 AST 节点是否包含危险操作。"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in self._allowed_imports:
                    raise ValueError(f"禁止导入模块：{top}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in self._allowed_imports:
                    raise ValueError(f"禁止导入模块：{top}")
        elif isinstance(node, ast.Call):
            self._check_call(node)

    def _check_call(self, node: ast.Call) -> None:
        """检查函数调用是否危险。"""
        if isinstance(node.func, ast.Name):
            if (None, node.func.id) in FORBIDDEN_FUNCTIONS:
                raise ValueError(f"禁止调用函数：{node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                attr_pair = (value.id, node.func.attr)
                if attr_pair in FORBIDDEN_FUNCTIONS:
                    raise ValueError(f"禁止调用函数：{value.id}.{node.func.attr}")

    @staticmethod
    def _set_resource_limits(memory_limit_mb: int) -> None:
        """在子进程中设置资源限制（仅 Unix 有效）。"""
        try:
            import resource  # noqa: PLC0415
        except ImportError:
            return

        max_bytes = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
        except ValueError:
            logger.debug("无法设置 RLIMIT_AS")

    async def run(
        self,
        script_path: Path,
        input_dir: Path,
        output_dir: Path,
        timeout: int = 60,
        memory_limit_mb: int = 512,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """在受限子进程中执行脚本。"""
        self._validate_script(script_path)
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["INPUT_DIR"] = str(input_dir)
        env["OUTPUT_DIR"] = str(output_dir)
        if extra_env:
            env.update(extra_env)
        # 默认清空 PYTHONPATH，避免加载额外模块；保留 PATH 以便找到 pandas 等依赖。
        env.pop("PYTHONPATH", None)

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                self._python,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(output_dir),
                preexec_fn=lambda: self._set_resource_limits(memory_limit_mb),
            )
        except NotImplementedError:
            # Windows 不支持 preexec_fn
            proc = await asyncio.create_subprocess_exec(
                self._python,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(output_dir),
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            exit_code = -1
            stderr_bytes += "\n[沙箱] 执行超时".encode("utf-8")
        finally:
            # 确保子进程被回收
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except asyncio.TimeoutError:
                    pass

        elapsed_ms = int((time.monotonic() - start) * 1000)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        output_files: dict[str, bytes] = {}
        if output_dir.exists():
            for file_path in output_dir.iterdir():
                if file_path.is_file():
                    try:
                        output_files[file_path.name] = file_path.read_bytes()
                    except OSError:
                        logger.warning("无法读取输出文件：%s", file_path)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            output_files=output_files,
            execution_time_ms=elapsed_ms,
        )
