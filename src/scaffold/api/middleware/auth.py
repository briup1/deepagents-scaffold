"""认证中间件。

支持通过 API key 请求头进行认证，可配置是否启用。
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class AuthMiddleware(BaseHTTPMiddleware):
    """通过 X-API-Key 请求头进行 API key 认证。"""

    def __init__(self, app: Any, *, api_key: str | None = None, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.api_key = api_key or os.getenv("SCAFFOLD_API_KEY")

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not self.enabled or not self.api_key:
            return await call_next(request)

        # 对 health、docs 和静态文件跳过认证
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
