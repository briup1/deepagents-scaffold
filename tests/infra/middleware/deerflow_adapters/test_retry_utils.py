"""Tests for shared retry utilities."""

from __future__ import annotations

from scaffold.infra.middleware.deerflow_adapters._retry_utils import (
    _build_retry_predicate,
    _extract_thread_id,
)


class TestBuildRetryPredicate:
    def test_status_code_match_returns_true(self):
        predicate = _build_retry_predicate([429, 502])

        class FakeException(Exception):
            status_code = 429

        assert predicate(FakeException("rate limited")) is True

    def test_status_code_miss_returns_false(self):
        predicate = _build_retry_predicate([429, 502])

        class FakeException(Exception):
            status_code = 500

        assert predicate(FakeException("server error")) is False

    def test_business_exception_returns_false(self):
        predicate = _build_retry_predicate([429, 502])

        assert predicate(ValueError("bad input")) is False


class TestExtractThreadId:
    def test_extracts_from_runtime_context(self):
        class FakeRuntime:
            context = {"thread_id": "thread-123"}

        class FakeRequest:
            runtime = FakeRuntime()

        assert _extract_thread_id(FakeRequest()) == "thread-123"

    def test_returns_none_when_runtime_is_none(self):
        class FakeRequest:
            runtime = None

        assert _extract_thread_id(FakeRequest()) is None
