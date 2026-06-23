"""Global error handler middleware.

Catches unhandled exceptions and returns standardized JSON error responses.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("scaffold.api.errors")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch all unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "-")
            tb = traceback.format_exc()
            logger.error(
                "Unhandled exception | %s %s | request_id=%s\n%s",
                request.method,
                request.url.path,
                request_id,
                tb,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "type": type(exc).__name__,
                },
            )
