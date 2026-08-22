"""代码执行沙箱抽象与实现。"""

from __future__ import annotations

from scaffold.infra.sandbox.base import Sandbox, SandboxResult
from scaffold.infra.sandbox.subprocess_sandbox import SubprocessSandbox

__all__ = ["Sandbox", "SandboxResult", "SubprocessSandbox"]
