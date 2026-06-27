"""Request ID 中间件。

为每个传入请求分配唯一请求 ID，用于链路追踪。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求和响应附加唯一的 request_id。"""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
