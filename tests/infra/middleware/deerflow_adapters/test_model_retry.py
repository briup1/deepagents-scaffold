"""Tests for ModelRetryAdapter."""

from __future__ import annotations

import logging

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage

from scaffold.infra.middleware.deerflow_adapters.model_retry import ModelRetryAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestModelRetryAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ModelRetryMiddleware")
        assert cls.__name__ == "ModelRetryAdapter"

    def test_default_params(self):
        mw = ModelRetryAdapter()
        assert mw._middleware.max_retries == 2
        assert mw._middleware.backoff_factor == 2.0
        assert mw._middleware.initial_delay == 1.0
        assert mw._middleware.max_delay == 60.0
        assert mw._middleware.jitter is True
        assert mw._middleware.on_failure == "continue"

    def test_custom_params(self):
        mw = ModelRetryAdapter(
            max_retries=5,
            backoff_factor=1.5,
            initial_delay=0.5,
            max_delay=30.0,
            jitter=False,
            retry_on_status_codes=[503],
        )
        assert mw._middleware.max_retries == 5
        assert mw._middleware.backoff_factor == 1.5
        assert mw._middleware.initial_delay == 0.5
        assert mw._middleware.max_delay == 30.0
        assert mw._middleware.jitter is False

    def test_wrap_model_call_delegates(self):
        mw = ModelRetryAdapter()
        expected = AIMessage(content="ok")

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])
        result = mw.wrap_model_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_model_call_delegates(self):
        mw = ModelRetryAdapter()
        expected = AIMessage(content="ok")

        class FakeMiddleware:
            async def awrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])

        async def handler(req):
            return expected

        result = await mw.awrap_model_call(request, handler)
        assert result is expected

    def test_logging_handler_logs_failed_attempt(self, caplog):
        mw = ModelRetryAdapter()

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return handler(request)

        mw._middleware = FakeMiddleware()

        class FakeException(Exception):
            status_code = 429

        class FakeRuntime:
            context = {"thread_id": "thread-abc"}

        request = ModelRequest(model=None, messages=[], runtime=FakeRuntime())

        with caplog.at_level(logging.WARNING):
            with pytest.raises(FakeException):
                mw.wrap_model_call(
                    request,
                    lambda req: (_ for _ in ()).throw(FakeException("rate limited")),
                )

        assert "thread-abc" in caplog.text
        assert "429" in caplog.text


class TestModelRetryStructuredLogging:
    def test_retry_emits_structured_events(self, caplog):
        """429 失败两次后成功：attempt 递增、字段齐全、最终 outcome=recovered。"""
        import logging

        from langchain_core.messages import AIMessage

        mw = ModelRetryAdapter(max_retries=2, initial_delay=0, jitter=False)
        calls = []

        class FakeException(Exception):
            status_code = 429

        fake_model = type("FakeModel", (), {"model": "primary-model"})()

        def handler(req):
            calls.append(1)
            if len(calls) < 3:
                raise FakeException("rate limited")
            return AIMessage(content="ok")

        request = ModelRequest(model=fake_model, messages=[])
        with caplog.at_level(logging.DEBUG):
            result = mw.wrap_model_call(request, handler)

        assert result.content == "ok"
        assert len(calls) == 3

        records = [r for r in caplog.records if getattr(r, "event", None) == "model_retry"]
        assert [r.attempt for r in records] == [1, 2, 3]
        assert [r.outcome for r in records] == ["failed", "failed", "recovered"]
        for r in records:
            assert r.model == "primary-model"
            assert isinstance(r.latency_ms, float)
        assert records[0].status_code == 429
        assert records[0].error == "FakeException"

    def test_exhaustion_logs_each_failed_attempt(self, caplog):
        """重试耗尽：每次失败都有结构化事件，attempt 递增到 max_retries+1。"""
        import logging

        mw = ModelRetryAdapter(max_retries=2, initial_delay=0, jitter=False)

        class FakeException(Exception):
            status_code = 429

        def handler(req):
            raise FakeException("rate limited")

        request = ModelRequest(model=None, messages=[])
        with caplog.at_level(logging.DEBUG):
            mw.wrap_model_call(request, handler)  # on_failure="continue" → 返回错误消息而非抛出

        records = [r for r in caplog.records if getattr(r, "event", None) == "model_retry"]
        assert [r.attempt for r in records] == [1, 2, 3]
        assert all(r.outcome == "failed" for r in records)
