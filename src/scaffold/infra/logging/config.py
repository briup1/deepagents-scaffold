"""日志配置。

支持级别选择、格式选择（text/json）以及输出目标（stderr/文件）。
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from scaffold.infra.logging.structured import JSONFormatter


def configure_logging(
    level: str = "info",
    *,
    format_type: str = "text",
    json_indent: int | None = None,
    handlers: list[logging.Handler] | None = None,
    log_file: str | None = None,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """为 scaffold 配置根日志。

    Args:
        level: 日志级别（debug/info/warning/error）。
        format_type: 'text' 或 'json'。
        json_indent: JSON 输出的缩进（None 表示紧凑）。
        handlers: 可选的自定义 handler（默认为 stderr + 文件）。
        log_file: 日志文件名（为 None 时使用默认名）。
        log_dir: 日志文件目录。
        max_bytes: 单个日志文件最大大小（默认 10MB）。
        backup_count: 保留的日志文件备份数量。
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("scaffold")
    root.setLevel(log_level)

    # 清除已有 handler，避免热重载时重复
    for h in list(root.handlers):
        root.removeHandler(h)

    if handlers is None:
        handlers = []

        # 1. stderr 输出
        stderr_handler = logging.StreamHandler(sys.stderr)
        handlers.append(stderr_handler)

        # 2. 文件输出
        os.makedirs(log_dir, exist_ok=True)
        file_name = log_file or "scaffold.log"
        file_path = os.path.join(log_dir, file_name)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    for handler in handlers:
        handler.setLevel(log_level)
        if format_type == "json":
            handler.setFormatter(JSONFormatter(indent=json_indent))
        else:
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        root.addHandler(handler)

    # 向子 logger 传播
    root.propagate = False

    # 同时设置常用库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
