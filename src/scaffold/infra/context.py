"""请求级上下文变量。

通过 contextvars 在 HTTP 层与 Agent 执行层之间透传 request_id / trace_id，
避免把内部追踪字段写入 agent state。
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("scaffold_request_id", default=None)
"""当前 HTTP 请求的 request_id，由 RequestIdMiddleware 生成。"""

trace_id_ctx: ContextVar[str | None] = ContextVar("scaffold_trace_id", default=None)
"""当前追踪链的 trace_id，通常与 request_id 一致，未来可对接 OpenTelemetry。"""

user_id_ctx: ContextVar[str] = ContextVar("scaffold_user_id", default="default")
"""当前请求的用户标识，由 AuthMiddleware 写入 request.state 后在 SSE 端点透传。"""


def get_request_id() -> str | None:
    """获取当前上下文中的 request_id。"""
    return request_id_ctx.get()


def get_trace_id() -> str | None:
    """获取当前上下文中的 trace_id；若未设置则回退到 request_id。"""
    return trace_id_ctx.get() or request_id_ctx.get()


def get_current_user_id() -> str:
    """获取当前上下文中的 user_id；未设置（如后台任务/测试）时为 'default'。"""
    return user_id_ctx.get()
