"""CORS 收紧（红线 9 相关）：禁止 allow_origins=['*'] + allow_credentials=True 组合。

默认仅放行前端开发源 http://localhost:3002；可用 CORS_ORIGINS 环境变量
（逗号分隔）覆盖。未设环境变量时本地开发行为保持不变。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scaffold.api.app import create_app


def _preflight(client: TestClient, origin: str) -> str | None:
    resp = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 200
    return resp.headers.get("access-control-allow-origin")


def _simple_request(client: TestClient, origin: str) -> str | None:
    """带 Origin 的简单请求：源不被允许时不回 allow-origin 头（响应仍 200）"""
    resp = client.get("/health", headers={"Origin": origin})
    assert resp.status_code == 200
    return resp.headers.get("access-control-allow-origin")


class TestCorsPolicy:
    def test_default_allows_frontend_dev_origin(self, client: TestClient) -> None:
        assert _preflight(client, "http://localhost:3002") == "http://localhost:3002"

    def test_default_rejects_unknown_origin(self, client: TestClient) -> None:
        assert _simple_request(client, "https://evil.example") is None
        assert _simple_request(client, "http://localhost:3000") is None

    def test_env_override_replaces_origin_list(
        self,
        _reset_app_config,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
        with TestClient(create_app()) as client:
            assert _preflight(client, "https://b.example") == "https://b.example"
            assert _simple_request(client, "http://localhost:3002") is None
