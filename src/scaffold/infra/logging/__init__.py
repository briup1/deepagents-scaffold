"""结构化日志系统。

提供 JSON 结构化日志、请求/响应中间件，
以及可配置的日志级别。
"""

from __future__ import annotations

from scaffold.infra.logging.config import configure_logging
from scaffold.infra.logging.middleware import LoggingMiddleware
from scaffold.infra.logging.structured import JSONFormatter, get_logger

__all__ = [
    "configure_logging",
    "LoggingMiddleware",
    "JSONFormatter",
    "get_logger",
]
