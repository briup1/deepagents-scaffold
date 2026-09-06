"""沙箱进程回收超时不静默吞异常（红线 4）。

kill 后 2s 内进程仍未退出时，finally 块的等待超时是被忽略的（不中断主流程），
但忽略前必须记录 warning（含沙箱类型），禁止静默 pass。
"""

from __future__ import annotations

import asyncio as asyncio_mod
import logging
from pathlib import Path
from typing import Any

import pytest

from scaffold.infra.sandbox.bwrap_sandbox import BwrapSandbox
from scaffold.infra.sandbox.subprocess_sandbox import SubprocessSandbox


class _StuckProc:
    """模拟 kill 后仍不退出、returncode 始终为 None 的僵尸进程。"""

    returncode: int | None = None

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""

    def kill(self) -> None:
        return None


async def _fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> _StuckProc:
    return _StuckProc()


async def _fake_wait_for(coro: Any, timeout: float | None = None) -> Any:
    """回收阶段（timeout=2）一律超时，其余调用正常透传。"""
    if timeout == 2:
        coro.close()
        raise TimeoutError
    return await coro


def _script(tmp_path: Path) -> Path:
    script = tmp_path / "main.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    return script


@pytest.mark.parametrize(
    ("sandbox", "sandbox_type"),
    [(SubprocessSandbox(), "subprocess"), (BwrapSandbox(), "bwrap")],
)
async def test_cleanup_timeout_logs_warning(
    sandbox: SubprocessSandbox,
    sandbox_type: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """回收超时忽略前必须留下含沙箱类型的 warning（红线 4）。"""
    monkeypatch.setattr(asyncio_mod, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(asyncio_mod, "wait_for", _fake_wait_for)

    with caplog.at_level(logging.WARNING, logger="scaffold.infra.sandbox"):
        result = await sandbox.run(
            _script(tmp_path),
            tmp_path / "in",
            tmp_path / "out",
            timeout=60,
        )

    assert result.exit_code == 0
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and sandbox_type in r.getMessage() and "回收" in r.getMessage()
    ]
    assert len(warnings) == 1, f"期望 1 条 {sandbox_type} 回收超时 warning，实际: {caplog.records}"
