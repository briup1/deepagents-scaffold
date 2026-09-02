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


class TestToolRetryStructuredLogging:
    def test_retry_emits_structured_events(self, caplog):
        """工具失败一次后成功：event=tool_retry、attempt 递增、最终 recovered。"""
        import logging

        mw = ToolRetryAdapter(max_retries=1, initial_delay=0, jitter=False)
        calls = []

        class FakeException(Exception):
            status_code = 502

        def handler(req):
            calls.append(1)
            if len(calls) < 2:
                raise FakeException("bad gateway")
            return ToolMessage(content="ok", tool_call_id="call-1")

        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "upload_file"},
            tool=None,
            state={},
            runtime=None,
        )
        with caplog.at_level(logging.DEBUG):
            result = mw.wrap_tool_call(request, handler)

        assert result.content == "ok"
        assert len(calls) == 2

        records = [r for r in caplog.records if getattr(r, "event", None) == "tool_retry"]
        assert [r.attempt for r in records] == [1, 2]
        assert [r.outcome for r in records] == ["failed", "recovered"]
        assert all(r.tool == "upload_file" for r in records)
        assert all(isinstance(r.latency_ms, float) for r in records)

    def test_tool_retry_converges_to_one_retry(self, caplog):
        """持续失败时恰好调用 2 次（初始 + 1 次重试）后收敛。"""
        import logging

        mw = ToolRetryAdapter(max_retries=1, initial_delay=0, jitter=False)
        calls = []

        class FakeException(Exception):
            status_code = 502

        def handler(req):
            calls.append(1)
            raise FakeException("bad gateway")

        request = ToolCallRequest(tool_call={"id": "call-1", "name": "tool"}, tool=None, state={}, runtime=None)
        with caplog.at_level(logging.DEBUG):
            mw.wrap_tool_call(request, handler)  # on_failure="continue" → 返回错误 ToolMessage

        assert len(calls) == 2
