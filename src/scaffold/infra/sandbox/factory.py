"""沙箱工厂：根据配置选择代码执行沙箱实现。"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.sandbox.base import Sandbox
from scaffold.infra.sandbox.bwrap_sandbox import BwrapSandbox
from scaffold.infra.sandbox.subprocess_sandbox import SubprocessSandbox

logger = logging.getLogger(__name__)


def get_sandbox(app_config: AppConfig | None = None) -> Sandbox:
    """根据配置返回对应的代码执行沙箱实例。

    当前支持的 provider：
    - ``subprocess``：受限子进程沙箱（AST 扫描，无系统级隔离）
    - ``bwrap``：bubblewrap 本地隔离沙箱（推荐；需一次性 AppArmor 配置）
    - ``docker`` / ``e2b``：占位，尚未实现；传入会抛出 NotImplementedError
    """
    if app_config is None:
        app_config = get_app_config()

    config = app_config.execution_sandbox
    provider = config.provider.lower()

    if provider == "subprocess":
        allowed_imports = set(config.allowed_imports) if config.allowed_imports else None
        return SubprocessSandbox(
            python_executable=None,
            allowed_imports=allowed_imports,
        )

    if provider == "bwrap":
        allowed_imports = set(config.allowed_imports) if config.allowed_imports else None
        return BwrapSandbox(allowed_imports=allowed_imports)

    if provider == "docker":
        raise NotImplementedError(
            "Docker sandbox provider is not yet implemented. "
            "Implement DockerSandbox in src/scaffold/infra/sandbox/docker_sandbox.py and register it here."
        )

    if provider == "e2b":
        raise NotImplementedError(
            "E2B sandbox provider is not yet implemented. "
            "Install e2b and implement E2BSandbox in src/scaffold/infra/sandbox/e2b_sandbox.py and register it here."
        )

    raise ValueError(f"Unknown sandbox provider: {config.provider}")


def create_sandbox(
    provider: str,
    *,
    allowed_imports: list[str] | None = None,
    **kwargs: Any,
) -> Sandbox:
    """根据显式 provider 构造沙箱，主要用于测试或脚本，不依赖全局配置。"""
    provider = provider.lower()

    if provider == "subprocess":
        return SubprocessSandbox(
            python_executable=kwargs.get("python_executable"),
            allowed_imports=set(allowed_imports) if allowed_imports else None,
        )

    if provider == "bwrap":
        return BwrapSandbox(
            python_executable=kwargs.get("python_executable"),
            allowed_imports=set(allowed_imports) if allowed_imports else None,
        )

    raise NotImplementedError(f"Sandbox provider '{provider}' is not implemented")
