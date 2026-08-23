"""沙箱执行模块。"""

from __future__ import annotations

from scaffold.infra.sandbox.base import Sandbox, SandboxResult
from scaffold.infra.sandbox.factory import create_sandbox, get_sandbox
from scaffold.infra.sandbox.subprocess_sandbox import SubprocessSandbox

__all__ = [
    "Sandbox",
    "SandboxResult",
    "SubprocessSandbox",
    "create_sandbox",
    "get_sandbox",
]
