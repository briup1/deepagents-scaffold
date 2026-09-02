"""Tests for ModelFallbackAdapter."""

from __future__ import annotations

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.middleware.deerflow_adapters.model_fallback import ModelFallbackAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestModelFallbackAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ModelFallbackMiddleware")
        assert cls.__name__ == "ModelFallbackAdapter"

    def test_resolves_fallback_models_and_creates_middleware(self, monkeypatch):
        calls = []

        def fake_create_chat_model(config, **kwargs):
            calls.append(config)
            return type(f"Fake{config.name}", (), {"model": config.model})()

        monkeypatch.setattr(
            "scaffold.infra.middleware.deerflow_adapters.model_fallback.create_chat_model",
            fake_create_chat_model,
        )

        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
            ModelConfig(name="fallback-1", display_name="Fallback 1", use="fake:Fallback1", model="fallback-1"),
        ]

        mw = ModelFallbackAdapter(models=models, fallback_models=["fallback-1"])

        assert len(calls) == 1
        assert calls[0].name == "fallback-1"
        assert len(mw._middleware.models) == 1

    def test_unknown_fallback_model_raises(self):
        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
        ]

        with pytest.raises(ValueError, match="Model 'missing' not found"):
            ModelFallbackAdapter(models=models, fallback_models=["missing"])

    def test_wrap_model_call_delegates(self):
        mw = ModelFallbackAdapter.__new__(ModelFallbackAdapter)
        expected = AIMessage(content="fallback ok")

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])
        result = mw.wrap_model_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_model_call_delegates(self):
        mw = ModelFallbackAdapter.__new__(ModelFallbackAdapter)
        expected = AIMessage(content="fallback ok")

        class FakeMiddleware:
            async def awrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])

        async def handler(req):
            return expected

        result = await mw.awrap_model_call(request, handler)
        assert result is expected


class TestModelFallbackStructuredLogging:
    def test_fallback_emits_structured_event(self, monkeypatch, caplog):
        """主模型持续失败：切换到备用模型并输出 event=model_fallback 结构化日志。"""
        import logging

        def fake_create_chat_model(config, **kwargs):
            return type(f"Fake{config.name}", (), {"model": config.model})()

        monkeypatch.setattr(
            "scaffold.infra.middleware.deerflow_adapters.model_fallback.create_chat_model",
            fake_create_chat_model,
        )

        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
            ModelConfig(name="fallback-1", display_name="Fallback 1", use="fake:Fallback1", model="fallback-1"),
        ]
        mw = ModelFallbackAdapter(models=models, fallback_models=["fallback-1"])

        primary = type("FakePrimary", (), {"model": "primary"})()
        calls = []

        def handler(req):
            calls.append(req.model.model)
            if req.model.model == "primary":
                raise RuntimeError("primary down")
            return AIMessage(content="recovered by fallback")

        request = ModelRequest(model=primary, messages=[])
        with caplog.at_level(logging.DEBUG):
            result = mw.wrap_model_call(request, handler)

        assert result.content == "recovered by fallback"
        assert calls == ["primary", "fallback-1"]

        records = [r for r in caplog.records if getattr(r, "event", None) == "model_fallback"]
        assert len(records) == 1
        assert records[0].model == "fallback-1"
        assert records[0].attempt == 2
        assert records[0].outcome == "activated"

    def test_all_models_failed_reraises(self, monkeypatch):
        """主备全部失败：最后异常原样抛出（由上层转为可读错误）。"""

        def fake_create_chat_model(config, **kwargs):
            return type(f"Fake{config.name}", (), {"model": config.model})()

        monkeypatch.setattr(
            "scaffold.infra.middleware.deerflow_adapters.model_fallback.create_chat_model",
            fake_create_chat_model,
        )

        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
            ModelConfig(name="fallback-1", display_name="Fallback 1", use="fake:Fallback1", model="fallback-1"),
        ]
        mw = ModelFallbackAdapter(models=models, fallback_models=["fallback-1"])

        request = ModelRequest(model=type("FakePrimary", (), {"model": "primary"})(), messages=[])
        with pytest.raises(RuntimeError, match="all down"):
            mw.wrap_model_call(request, lambda req: (_ for _ in ()).throw(RuntimeError("all down")))
