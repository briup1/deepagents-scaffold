"""Logging configuration.

Supports level selection, format choice (text/json), and output targets.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from scaffold.infra.logging.structured import JSONFormatter


def configure_logging(
    level: str = "info",
    *,
    format_type: str = "text",
    json_indent: int | None = None,
    handlers: list[logging.Handler] | None = None,
) -> None:
    """Configure root logging for the scaffold.

    Args:
        level: Log level (debug/info/warning/error).
        format_type: 'text' or 'json'.
        json_indent: Indent for JSON output (None = compact).
        handlers: Optional custom handlers (defaults to stderr).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("scaffold")
    root.setLevel(log_level)

    # Clear existing handlers to avoid duplication on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    if handlers is None:
        handler = logging.StreamHandler(sys.stderr)
        handlers = [handler]

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

    # Propagate to children
    root.propagate = False

    # Also set common library loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
