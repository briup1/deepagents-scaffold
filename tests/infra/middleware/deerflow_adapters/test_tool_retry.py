"""Tests for ToolRetryAdapter."""

from __future__ import annotations

import logging

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from scaffold.infra.middleware.deerflow_adapters.tool_retry import ToolRetryAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestToolRetryAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ToolRetryMiddleware")
        assert cls.__name__ == "ToolRetryAdapter"

    def test_default_max_retries_is_one(self):
        mw = ToolRetryAdapter()
        assert mw._middleware.max_retries == 1
        assert mw._middleware.jitter is True

    def test_custom_params(self):
        mw = ToolRetryAdapter(max_retries=3, retry_on_status_codes=[429])
        assert mw._middleware.max_retries == 3

    def test_wrap_tool_call_delegates(self):
        mw = ToolRetryAdapter()
        expected = ToolMessage(content="ok", tool_call_id="call-1")

        class FakeMiddleware:
            def wrap_tool_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "tool"},
            tool=None,
            state={},
            runtime=None,
        )
        result = mw.wrap_tool_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_tool_call_delegates(self):
        mw = ToolRetryAdapter()
        expected = ToolMessage(content="ok", tool_call_id="call-2")

        class FakeMiddleware:
            async def awrap_tool_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ToolCallRequest(
            tool_call={"id": "call-2", "name": "tool"},
            tool=None,
            state={},
            runtime=None,
        )

        async def handler(req):
            return expected

        result = await mw.awrap_tool_call(request, handler)
        assert result is expected

    def test_logging_handler_logs_failed_attempt(self, caplog):
        mw = ToolRetryAdapter()

        class FakeMiddleware:
            def wrap_tool_call(self, request, handler):
                return handler(request)

        mw._middleware = FakeMiddleware()

        class FakeException(Exception):
            status_code = 502

        class FakeRuntime:
            context = {"thread_id": "thread-tool"}

        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "tool"},
            tool=None,
            state={},
            runtime=FakeRuntime(),
        )

        with caplog.at_level(logging.WARNING):
            with pytest.raises(FakeException):
                mw.wrap_tool_call(
                    request,
                    lambda req: (_ for _ in ()).throw(FakeException("bad gateway")),
                )

        assert "thread-tool" in caplog.text
        assert "502" in caplog.text
