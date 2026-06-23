"""Structured logging system.

Provides JSON-structured logging, request/response middleware,
and configurable log levels.
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
