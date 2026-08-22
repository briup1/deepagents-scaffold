"""代码执行沙箱抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class SandboxResult(BaseModel):
    """沙箱执行结果。"""

    stdout: str
    stderr: str
    exit_code: int
    output_files: dict[str, bytes]
    execution_time_ms: int


class Sandbox(ABC):
    """代码执行沙箱抽象。"""

    @abstractmethod
    async def run(
        self,
        script_path: Path,
        input_dir: Path,
        output_dir: Path,
        timeout: int = 60,
        memory_limit_mb: int = 512,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """在沙箱中执行脚本。

        Args:
            script_path: 待执行的 Python 脚本路径。
            input_dir: 只读输入目录。
            output_dir: 只写输出目录。
            timeout: 执行超时时间（秒）。
            memory_limit_mb: 内存限制（MB）。

        Returns:
            执行结果，包含标准输出/错误、退出码、输出文件和执行耗时。
        """
