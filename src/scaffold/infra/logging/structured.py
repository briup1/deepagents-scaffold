"""JSON 结构化日志格式化器。"""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Any

from scaffold.infra.context import get_request_id

# 常见敏感模式：sk- 前缀密钥（长度≥8 才判定为密钥）；api_key/token/secret/password 赋值或头形态
_SK_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_SECRET_ASSIGN_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|x-api-key|token|secret|password)(['\"]?\s*[:=]\s*['\"]?)([^\s,'\"}]+)"
)


def mask_sensitive(text: str) -> str:
    """对日志文本中的常见敏感模式做掩码，不改变其余内容。"""
    text = _SK_KEY_PATTERN.sub("sk-***", text)
    return _SECRET_ASSIGN_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


class RequestIdFilter(logging.Filter):
    """自动从 ContextVar 读取 request_id 并注入 LogRecord。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


# logging.LogRecord 的标准属性；其余 record 属性（即 extra={...} 注入的）全部并入 JSON
_RESERVED_ATTRS = frozenset(logging.makeLogRecord({}).__dict__)


class SensitiveDataFilter(logging.Filter):
    """对日志消息与参数中的敏感模式做掩码（红线 9：生产日志禁止打印敏感信息）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(mask_sensitive(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: mask_sensitive(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


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
