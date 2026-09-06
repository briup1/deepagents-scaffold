"""基于 bubblewrap 的本地隔离沙箱。

通过 Linux namespaces 提供真实隔离：文件系统只读白名单挂载、断网、
--die-with-parent 级联清理。内存限制沿用 RLIMIT_AS（preexec_fn 设置，
bwrap 子进程继承），超时沿用 asyncio timeout + kill。

部署前置（Ubuntu 23.10+）：内核默认用 AppArmor 限制 unprivileged userns，
需一次性执行 scripts/setup_bwrap_apparmor.sh（sudo）放行 bwrap。
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from scaffold.infra.sandbox.base import SandboxResult
from scaffold.infra.sandbox.subprocess_sandbox import SubprocessSandbox

logger = logging.getLogger(__name__)

# 沙箱内布局：/work/in（只读输入）、/work/out（可写输出）、/work/<脚本名>
SANDBOX_INPUT = "/work/in"
SANDBOX_OUTPUT = "/work/out"


class BwrapSandbox(SubprocessSandbox):
    """bubblewrap 隔离沙箱（继承 AST 静态扫描，叠加内核级隔离）。"""

    def __init__(
        self,
        python_executable: str | None = None,
        allowed_imports: set[str] | None = None,
        bwrap_executable: str = "bwrap",
    ) -> None:
        super().__init__(python_executable, allowed_imports)
        self._bwrap = bwrap_executable

    def _venv_root(self) -> Path | None:
        """若解释器位于 <venv>/bin/python 布局，返回 venv 根目录（需挂载进沙箱）。"""
        exe = Path(self._python)
        if exe.parent.name == "bin" and (exe.parent.parent / "pyvenv.cfg").exists():
            return exe.parent.parent
        return None

    @staticmethod
    def _map_env_value(value: str, input_dir: Path, output_dir: Path) -> str:
        """把 extra_env 中的宿主机路径前缀替换为沙箱内路径。"""
        for host_prefix, sandbox_prefix in ((str(output_dir), SANDBOX_OUTPUT), (str(input_dir), SANDBOX_INPUT)):
            if value.startswith(host_prefix):
                return sandbox_prefix + value[len(host_prefix) :]
        return value

    def _build_args(
        self,
        script_path: Path,
        input_dir: Path,
        output_dir: Path,
        extra_env: dict[str, str] | None,
    ) -> list[str]:
        args = [
            self._bwrap,
            "--unshare-all",
            "--unshare-net",
            "--die-with-parent",
            "--clearenv",
            # Python 运行时（系统目录 + venv）
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/bin",
            "/bin",
        ]
        if Path("/lib64").exists():
            args += ["--ro-bind", "/lib64", "/lib64"]
        venv_root = self._venv_root()
        if venv_root is not None:
            args += ["--ro-bind", str(venv_root), str(venv_root)]
        # 工作区：输入只读、输出可写、脚本只读
        args += [
            "--ro-bind",
            str(input_dir),
            SANDBOX_INPUT,
            "--ro-bind",
            str(script_path),
            f"/work/{script_path.name}",
            "--bind",
            str(output_dir),
            SANDBOX_OUTPUT,
            "--tmpfs",
            "/tmp",
            "--chdir",
            SANDBOX_OUTPUT,
        ]
        # 最小环境变量
        args += [
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "INPUT_DIR",
            SANDBOX_INPUT,
            "--setenv",
            "OUTPUT_DIR",
            SANDBOX_OUTPUT,
        ]
        for key, value in (extra_env or {}).items():
            args += ["--setenv", key, self._map_env_value(value, input_dir, output_dir)]
        args += [self._python, f"/work/{script_path.name}"]
        return args

    async def run(
        self,
        script_path: Path,
        input_dir: Path,
        output_dir: Path,
        timeout: int = 60,
        memory_limit_mb: int = 512,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """在 bubblewrap 命名空间中执行脚本。"""
        self._validate_script(script_path)
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        args = self._build_args(script_path, input_dir, output_dir, extra_env)

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=lambda: self._set_resource_limits(memory_limit_mb),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"bwrap 不可用（{exc}）。请安装 bubblewrap；Ubuntu 23.10+ 还需执行 "
                "scripts/setup_bwrap_apparmor.sh 放行 unprivileged userns。"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode or 0
        except TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            exit_code = -1
            stderr_bytes += "\n[沙箱] 执行超时".encode("utf-8")
        finally:
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except TimeoutError:
                    # 超时不中断主流程，但禁止静默忽略（红线 4）：进程可能已成僵尸，需留痕排查
                    logger.warning("bwrap 沙箱：进程 kill 后 2s 内仍未退出，放弃回收（不影响主流程）")

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
