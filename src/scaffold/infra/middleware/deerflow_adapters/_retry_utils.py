"""Shared helpers for retry and fallback middleware adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _build_retry_predicate(status_codes: list[int]) -> Callable[[Exception], bool]:
    """Build a callable that decides whether an exception should be retried.

    Matches first by ``status_code`` attribute, then by known provider
    rate-limit/timeout exception types. Business exceptions like ``ValueError``
    are not retried.
    """
    status_set = set(status_codes)

    def should_retry(exc: Exception) -> bool:
        code = getattr(exc, "status_code", None)
        if code is not None and code in status_set:
            logger.warning("Retry predicate matched status_code=%s", code)
            return True

        # Delayed imports keep the helper usable even when a provider
        # package is not installed.
        for module_path, class_name in (
            ("openai", "RateLimitError"),
            ("openai", "APITimeoutError"),
            ("openai", "InternalServerError"),
            ("anthropic", "RateLimitError"),
            ("anthropic", "APITimeoutError"),
            ("anthropic", "InternalServerError"),
            ("httpx", "TimeoutException"),
            ("httpx", "ConnectError"),
        ):
            try:
                module = __import__(module_path, fromlist=[class_name])
                exc_cls = getattr(module, class_name)
                if isinstance(exc, exc_cls):
                    logger.warning(
                        "Retry predicate matched provider exception %s.%s",
                        module_path,
                        class_name,
                    )
                    return True
            except Exception:
                continue

        return False

    return should_retry


def _extract_thread_id(request: Any) -> str | None:
    """Extract thread_id from a ModelRequest's runtime context, if available."""
    runtime = getattr(request, "runtime", None)
    if runtime is None:
        return None
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        return context.get("thread_id")
    return None
