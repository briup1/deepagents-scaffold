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
