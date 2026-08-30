"""JSON 结构化日志格式化器。"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from scaffold.infra.context import get_request_id


class RequestIdFilter(logging.Filter):
    """自动从 ContextVar 读取 request_id 并注入 LogRecord。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


# logging.LogRecord 的标准属性；其余 record 属性（即 extra={...} 注入的）全部并入 JSON
_RESERVED_ATTRS = frozenset(logging.makeLogRecord({}).__dict__)


class JSONFormatter(logging.Formatter):
    """将日志记录格式化为 JSON 行。"""

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
        # 合入 extra={...} 注入的结构化字段（如 event/model/attempt）
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key not in payload and key != "extra":
                payload[key] = value
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(record.extra)

        return json.dumps(payload, indent=self.indent, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """获取一个 scaffold 命名空间的 logger。"""
    return logging.getLogger(f"scaffold.{name}")
