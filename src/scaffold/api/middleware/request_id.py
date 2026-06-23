"""Request ID middleware.

Assigns a unique request ID to every incoming request for tracing.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request and response."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
