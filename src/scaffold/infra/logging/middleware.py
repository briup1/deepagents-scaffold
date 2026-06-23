"""FastAPI request/response logging middleware."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("scaffold.api")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with timing, method, path, and status."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", "-")

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "Request failed | %s %s | %.2fms | error=%s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
                extra={"request_id": request_id},
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Request | %s %s | %d | %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response
