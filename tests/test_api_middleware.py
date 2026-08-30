"""Direct unit tests for FastAPI gateway middleware.

Each middleware is instantiated with a minimal FastAPI app and exercised
via TestClient without using create_app().
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from scaffold.api.middleware.auth import AuthMiddleware
from scaffold.api.middleware.error_handler import ErrorHandlerMiddleware
from scaffold.api.middleware.rate_limit import RateLimitMiddleware
from scaffold.api.middleware.request_id import RequestIdMiddleware
from scaffold.infra.logging.middleware import LoggingMiddleware


# ---------------------------------------------------------------------------
# AuthMiddleware
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    def _make_app(self, **kwargs: Any) -> FastAPI:
        app = FastAPI()
        app.add_middleware(AuthMiddleware, **kwargs)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/api/data")
        def data(request: Request):
            return {"data": "value", "user_id": getattr(request.state, "user_id", None)}

        @app.post("/agent/default")
        def agent_sse():
            return {"ok": True}

        return app

    USERS = {"token-alice": "alice", "token-bob": "bob"}

    def test_disabled_allows_all_with_default_user(self):
        app = self._make_app(enabled=False, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get("/api/data")
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "default"

    def test_enabled_empty_users_allows_all(self):
        app = self._make_app(enabled=True, token_users={})
        client = TestClient(app)
        assert client.get("/api/data").status_code == 200

    def test_enabled_missing_header_returns_401(self):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get("/api/data")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or missing API key"

    def test_enabled_wrong_token_returns_401(self):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get("/api/data", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_alice_token_maps_to_alice_user_id(self):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get("/api/data", headers={"X-API-Key": "token-alice"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "alice"

    def test_bob_token_maps_to_bob_user_id(self):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get("/api/data", headers={"X-API-Key": "token-bob"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "bob"

    def test_agent_sse_endpoint_requires_auth(self):
        """/agent 不再豁免：无凭证必须 401。"""
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        assert client.post("/agent/default").status_code == 401
        assert client.post("/agent/default", headers={"X-API-Key": "token-alice"}).status_code == 200

    def test_health_skips_auth(self):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        assert client.get("/health").status_code == 200

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_docs_and_openapi_skip_auth(self, path: str):
        app = self._make_app(enabled=True, token_users=self.USERS)
        client = TestClient(app)
        resp = client.get(path)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# RequestIdMiddleware
# ---------------------------------------------------------------------------


class TestRequestIdMiddleware:
    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        @app.get("/")
        def root(request: Request):
            return {"request_id": request.state.request_id}

        return app

    def test_generates_uuid_when_no_header(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["request_id"]
        assert "-" in body["request_id"]
        assert resp.headers["X-Request-ID"] == body["request_id"]

    def test_preserves_client_provided_request_id(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/", headers={"X-Request-ID": "client-id-123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["request_id"] == "client-id-123"
        assert resp.headers["X-Request-ID"] == "client-id-123"

    def test_sets_request_state(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/", headers={"X-Request-ID": "abc"})
        assert resp.json()["request_id"] == "abc"

    def test_response_has_header(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/")
        assert "X-Request-ID" in resp.headers


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    def _make_app(self, **kwargs: Any) -> FastAPI:
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, **kwargs)

        @app.get("/")
        def root():
            return {"ok": True}

        return app

    def test_disabled_allows_unlimited(self):
        app = self._make_app(enabled=False, requests_per_minute=1, window_seconds=60)
        client = TestClient(app)
        for _ in range(5):
            assert client.get("/").status_code == 200

    def test_limit_2_allows_2_requests(self):
        app = self._make_app(enabled=True, requests_per_minute=2, window_seconds=60)
        client = TestClient(app)
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 200

    def test_limit_1_second_request_429(self):
        app = self._make_app(enabled=True, requests_per_minute=1, window_seconds=60)
        client = TestClient(app)
        assert client.get("/").status_code == 200
        resp = client.get("/")
        assert resp.status_code == 429
        body = resp.json()
        assert "detail" in body
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)

    async def test_different_ips_have_separate_counters(self):
        middleware = RateLimitMiddleware(
            app=None,  # type: ignore[arg-type]
            requests_per_minute=1,
            window_seconds=60,
            enabled=True,
        )
        call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

        def _req(host: str) -> MagicMock:
            r = MagicMock()
            r.client = MagicMock()
            r.client.host = host
            return r

        # Client A first request → pass
        assert (await middleware.dispatch(_req("1.1.1.1"), call_next)).status_code == 200
        # Client B first request → pass (separate counter)
        assert (await middleware.dispatch(_req("2.2.2.2"), call_next)).status_code == 200
        # Client A second request → blocked
        assert (await middleware.dispatch(_req("1.1.1.1"), call_next)).status_code == 429
        # Client B second request → blocked
        assert (await middleware.dispatch(_req("2.2.2.2"), call_next)).status_code == 429

    def test_window_expires_allows_again(self):
        app = self._make_app(enabled=True, requests_per_minute=1, window_seconds=0.1)
        client = TestClient(app)
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 429
        time.sleep(0.15)
        assert client.get("/").status_code == 200


# ---------------------------------------------------------------------------
# ErrorHandlerMiddleware
# ---------------------------------------------------------------------------


class TestErrorHandlerMiddleware:
    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        def error():
            raise ValueError("boom")

        @app.get("/ok")
        def ok():
            return {"ok": True}

        return app

    def test_route_raises_valueerror_returns_500(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/error")
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert "request_id" in body
        assert body["type"] == "ValueError"

    def test_includes_request_id_from_state(self):
        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        def error(request: Request):
            request.state.request_id = "req-42"
            raise ValueError("boom")

        client = TestClient(app)
        resp = client.get("/error")
        assert resp.json()["request_id"] == "req-42"

    def test_normal_request_passes_through_unchanged(self):
        app = self._make_app()
        client = TestClient(app)
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------


class TestLoggingMiddleware:
    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.get("/ok")
        def ok():
            return {"ok": True}

        @app.get("/fail")
        def fail():
            raise RuntimeError("boom")

        return app

    def test_successful_request_logs_info(self):
        app = self._make_app()
        client = TestClient(app)

        with patch("scaffold.infra.logging.middleware.logger") as mock_logger:
            resp = client.get("/ok")

        assert resp.status_code == 200
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[0]
        assert args[1] == "GET"
        assert args[2] == "/ok"
        assert args[3] == 200
        assert args[4] >= 0

    def test_logs_error_when_call_next_raises(self):
        """When no ErrorHandler sits inside, call_next propagates the exception."""
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.get("/fail")
        def fail():
            raise RuntimeError("boom")

        client = TestClient(app)
        with patch("scaffold.infra.logging.middleware.logger") as mock_logger:
            with pytest.raises(RuntimeError, match="boom"):
                client.get("/fail")

        mock_logger.error.assert_called_once()
        args = mock_logger.error.call_args[0]
        assert args[1] == "GET"
        assert args[2] == "/fail"
        assert args[3] >= 0
        assert isinstance(args[4], RuntimeError)

    def test_logs_info_for_500_when_error_handler_is_inner(self):
        """Production config: ErrorHandler catches exceptions; Logging sees the 500 JSONResponse."""
        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)  # innermost
        app.add_middleware(LoggingMiddleware)  # outer

        @app.get("/fail")
        def fail():
            raise RuntimeError("boom")

        client = TestClient(app)
        with patch("scaffold.infra.logging.middleware.logger") as mock_logger:
            resp = client.get("/fail")

        assert resp.status_code == 500
        # LoggingMiddleware sees a normal JSONResponse return from call_next,
        # so it logs INFO (not ERROR) even though the status code is 500.
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[0]
        assert args[3] == 500
        mock_logger.error.assert_not_called()

    def test_log_record_has_request_id_extra(self):
        app = FastAPI()
        # RequestId must be *inside* Logging so that request.state.request_id
        # is already set when LoggingMiddleware reads it.
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestIdMiddleware)

        @app.get("/ok")
        def ok():
            return {"ok": True}

        client = TestClient(app)
        with patch("scaffold.infra.logging.middleware.logger") as mock_logger:
            client.get("/ok", headers={"X-Request-ID": "req-99"})

        mock_logger.info.assert_called_once()
        kwargs = mock_logger.info.call_args[1]
        assert kwargs["extra"]["request_id"] == "req-99"


# ---------------------------------------------------------------------------
# Integration: Stack Order Verification
# ---------------------------------------------------------------------------


class TestIntegrationStackOrder:
    @staticmethod
    def _build_app(**auth_kwargs: Any) -> FastAPI:
        """Build mini-app with middlewares in production order.

        FastAPI: last added = outermost.
        Production wrap order (inner -> outer):
            ErrorHandler -> Logging -> RateLimit -> RequestId -> Auth
        """
        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)  # innermost
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RateLimitMiddleware, enabled=True, requests_per_minute=10, window_seconds=60)
        app.add_middleware(RequestIdMiddleware)
        app.add_middleware(AuthMiddleware, **auth_kwargs)  # outermost

        @app.get("/health")
        def health():
            return {"status": "healthy"}

        @app.get("/api/data")
        def data():
            return {"data": "value"}

        @app.get("/error")
        def error():
            raise ValueError("boom")

        return app

    def test_authenticated_request_returns_200_with_request_id(self):
        app = self._build_app(enabled=True, token_users={"test-secret": "alice"})
        client = TestClient(app)
        resp = client.get("/api/data", headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers

    def test_exception_returns_500_with_request_id_and_json(self):
        app = self._build_app(enabled=True, token_users={"test-secret": "alice"})
        client = TestClient(app)
        resp = client.get("/error", headers={"X-API-Key": "test-secret"})
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert "request_id" in body
        assert body["type"] == "ValueError"
        # ErrorHandlerMiddleware is innermost, so it catches the exception and
        # returns a JSONResponse. RequestIdMiddleware is outside it, so the
        # X-Request-ID header is added to the response. The body.request_id
        # comes from request.state.request_id set by RequestIdMiddleware before
        # the exception reached ErrorHandler.
        assert body["request_id"]
        assert "X-Request-ID" in resp.headers
        assert body["request_id"] == resp.headers["X-Request-ID"]

    def test_health_bypasses_auth_through_full_stack(self):
        app = self._build_app(enabled=True, token_users={"test-secret": "alice"})
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert "X-Request-ID" in resp.headers
