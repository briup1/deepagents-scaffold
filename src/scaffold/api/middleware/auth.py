"""Authentication middleware.

Supports API key header authentication with configurable enablement.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class AuthMiddleware(BaseHTTPMiddleware):
    """API key authentication via X-API-Key header."""

    def __init__(self, app: Any, *, api_key: str | None = None, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.api_key = api_key or os.getenv("SCAFFOLD_API_KEY")

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not self.enabled or not self.api_key:
            return await call_next(request)

        # Skip auth for health, docs, and static files
        path = request.url.path
        if path in ("/health", "/docs", "/redoc", "/openapi.json") or path.startswith("/static"):
            return await call_next(request)

        provided = request.headers.get("X-API-Key")
        if provided != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
