"""工具调用重试中间件适配器。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.tool_retry import ToolRetryMiddleware
from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.middleware.deerflow_adapters._retry_utils import (
    _build_retry_predicate,
    _extract_thread_id,
)

logger = logging.getLogger(__name__)

_DEFAULT_STATUS_CODES = [429, 502, 503, 504]


class ToolRetryAdapter(AgentMiddleware):
    """工具调用失败时按指数退避重试。

    Args:
        max_retries: 初始调用之外的最大重试次数。默认 1。
        backoff_factor: 退避倍数。默认 2.0。
        initial_delay: 首次重试前等待秒数。默认 1.0。
        max_delay: 退避增长上限。默认 60.0。
        jitter: 是否加入 ±25% 随机抖动。默认 True。
        retry_on_status_codes: 触发重试的 HTTP 状态码列表。
            默认 [429, 502, 503, 504]。
    """

    def __init__(
        self,
        *,
        max_retries: int = 1,
        backoff_factor: float = 2.0,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_on_status_codes: list[int] | None = None,
    ) -> None:
        self._middleware = ToolRetryMiddleware(
            max_retries=max_retries,
            retry_on=_build_retry_predicate(retry_on_status_codes or _DEFAULT_STATUS_CODES),
            on_failure="continue",
            backoff_factor=backoff_factor,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        return self._middleware.wrap_tool_call(request, self._wrap_sync_handler(request, handler))

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        return await self._middleware.awrap_tool_call(request, self._wrap_async_handler(request, handler))

    def _wrap_sync_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        def wrapped(req: Any) -> Any:
            try:
                return handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Tool call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped

    def _wrap_async_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        async def wrapped(req: Any) -> Any:
            try:
                return await handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Tool call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped
