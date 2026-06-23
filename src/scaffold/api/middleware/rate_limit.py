"""Rate limiting middleware.

Simple in-memory rate limiter per client IP.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit requests by client IP.

    Args:
        requests_per_minute: Max requests allowed per window.
        window_seconds: Time window in seconds.
    """

    def __init__(
        self,
        app: Any,
        *,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.limit = requests_per_minute
        self.window = window_seconds
        self._store: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not self.enabled:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        window_start = now - self.window
        self._store.setdefault(client_ip, [])
        self._store[client_ip] = [t for t in self._store[client_ip] if t > window_start]

        if len(self._store[client_ip]) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": int(self.window - (now - self._store[client_ip][0])),
                },
            )

        self._store[client_ip].append(now)
        return await call_next(request)
