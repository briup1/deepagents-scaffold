"""认证中间件。

多用户 token 认证：token → user_id 映射来自 config.yaml 的 auth 段。
认证通过后将 user_id 写入 request.state.user_id，供路由与 Agent 工具层使用。
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

EXEMPT_PATHS = ("/health", "/docs", "/redoc", "/openapi.json")
DEFAULT_USER_ID = "default"


class AuthMiddleware(BaseHTTPMiddleware):
    """通过 X-API-Key 请求头进行多用户 token 认证。

    Args:
        token_users: token → user_id 映射。
        enabled: 是否启用。禁用或映射为空时全放行，user_id 一律为 "default"。
    """

    def __init__(self, app: Any, *, token_users: dict[str, str] | None = None, enabled: bool = False) -> None:
        super().__init__(app)
        self.token_users = token_users or {}
        self.enabled = enabled and bool(self.token_users)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not self.enabled:
            request.state.user_id = DEFAULT_USER_ID
            return await call_next(request)

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        token = request.headers.get("X-API-Key")
        user_id = self.token_users.get(token) if token else None
        if user_id is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        request.state.user_id = user_id
        return await call_next(request)
