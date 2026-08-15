"""中间件测试的共享 fixture。

让中间件单元测试也能把结构化日志写入 logs/scaffold.log，
同时保证测试结束后恢复原始 logger 状态，不影响其他测试。
"""

from __future__ import annotations

import logging
from typing import Generator

import pytest

from scaffold.infra.logging.config import configure_logging


@pytest.fixture(scope="session", autouse=True)
def _enable_middleware_file_logging() -> Generator[None, None, None]:
    """为中间件测试启用文件日志，并在结束后恢复。"""
    scaffold_logger = logging.getLogger("scaffold")
    old_level = scaffold_logger.level
    old_handlers = list(scaffold_logger.handlers)
    old_propagate = scaffold_logger.propagate

    # 使用项目统一的日志配置，写入 logs/scaffold.log
    configure_logging(
        level="debug",
        format_type="json",
        log_dir="logs",
        log_file="scaffold.log",
    )

    yield

    # 恢复原始状态
    scaffold_logger.setLevel(old_level)
    scaffold_logger.handlers.clear()
    scaffold_logger.handlers.extend(old_handlers)
    scaffold_logger.propagate = old_propagate
