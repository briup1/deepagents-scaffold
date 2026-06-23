"""JSON structured log formatter."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def __init__(self, indent: int | None = None) -> None:
        self.indent = indent

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)
        if hasattr(record, "extra"):
            payload.update(record.extra)

        return json.dumps(payload, indent=self.indent, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get a scaffold-namespaced logger."""
    return logging.getLogger(f"scaffold.{name}")
