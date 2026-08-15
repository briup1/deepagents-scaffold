"""请求上下文（ContextVar）透传测试。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from scaffold.api.middleware.request_id import RequestIdMiddleware
from scaffold.infra.context import get_request_id, get_trace_id, request_id_ctx, trace_id_ctx


def test_get_request_id_returns_context_value():
    token = request_id_ctx.set("req-123")
    try:
        assert get_request_id() == "req-123"
        assert get_trace_id() == "req-123"
    finally:
        request_id_ctx.reset(token)


def test_get_trace_id_prefers_trace_id_over_request_id():
    req_token = request_id_ctx.set("req-123")
    trace_token = trace_id_ctx.set("trace-456")
    try:
        assert get_request_id() == "req-123"
        assert get_trace_id() == "trace-456"
    finally:
        trace_id_ctx.reset(trace_token)
        request_id_ctx.reset(req_token)


def test_request_id_propagates_to_async_generator():
    """验证 RequestIdMiddleware 设置的 request_id 能通过 ContextVar 透传到后台 Task。"""
    captured: list[dict[str, Any]] = []

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    async def streamer():
        captured.append(
            {
                "request_id": get_request_id(),
                "trace_id": get_trace_id(),
            }
        )
        yield b"data"

    @app.get("/test")
    async def endpoint(request: Request):
        req_id = getattr(request.state, "request_id", None)
        if req_id:
            request_id_ctx.set(req_id)
            trace_id_ctx.set(req_id)
        # 模拟 ag_ui.py 中 asyncio.create_task 的行为
        task = asyncio.create_task(_collect_from_stream())
        await task
        return {"ok": True}

    async def _collect_from_stream():
        async for _ in streamer():
            pass

    with TestClient(app) as client:
        response = client.get("/test", headers={"X-Request-ID": "external-req-789"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "external-req-789"

    assert len(captured) == 1
    assert captured[0]["request_id"] == "external-req-789"
    assert captured[0]["trace_id"] == "external-req-789"


def test_request_id_generated_when_header_missing():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/test")
    def endpoint(request: Request):
        return {"request_id": getattr(request.state, "request_id", None)}

    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        body = response.json()
        assert body["request_id"]
        assert response.headers["X-Request-ID"] == body["request_id"]
