"""Tests for the middleware framework."""

from __future__ import annotations

import pytest

from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.middleware.registry import get_middleware_registry


class TestMiddlewareRegistry:
    def test_resolve_known_alias(self):
        registry = get_middleware_registry()
        cls = registry.resolve("LoopDetectionMiddleware")
        assert cls.__name__ == "LoopDetectionMiddleware"

    def test_resolve_by_import_path(self):
        registry = get_middleware_registry()
        cls = registry.resolve(
            "scaffold.infra.middleware.deerflow_adapters.tool_error_handling:ToolErrorHandlingMiddleware"
        )
        assert cls.__name__ == "ToolErrorHandlingMiddleware"

    def test_resolve_unknown_raises(self):
        registry = get_middleware_registry()
        with pytest.raises(ValueError, match="Unknown middleware alias"):
            registry.resolve("NonExistentMiddleware")

    def test_list_known(self):
        registry = get_middleware_registry()
        names = registry.list_known()
        assert "LoopDetectionMiddleware" in names
        assert "ToolErrorHandlingMiddleware" in names


class TestMiddlewareFactory:
    def test_empty_chain(self):
        from scaffold.infra.config.middleware_config import MiddlewareChainConfig

        chain = MiddlewareChainConfig(items=[])
        result = build_middleware_chain(chain)
        assert result == []


class TestScaffoldSummarizationMiddleware:
    def test_alias_resolves(self):
        registry = get_middleware_registry()
        cls = registry.resolve("ScaffoldSummarizationMiddleware")
        assert cls.__name__ == "SummarizationMiddleware"

    def test_wrapper_injects_model_from_config(self, monkeypatch):
        import scaffold.infra.config.app_config as app_config_module
        import scaffold.infra.models.factory as model_factory_module

        fake_model = type("FakeModel", (), {"_llm_type": "fake"})()

        class FakeModelConfig:
            name = "fake-model"
            use = "fake:FakeModel"

        class FakeAppConfig:
            models = [FakeModelConfig()]

            def get_model_config(self, name):
                return FakeModelConfig() if name == "fake-model" else None

        monkeypatch.setattr(
            app_config_module, "get_app_config", lambda config_path=None: FakeAppConfig()
        )
        calls = []

        def fake_create_chat_model(cfg, **kwargs):
            calls.append(cfg)
            return fake_model

        monkeypatch.setattr(model_factory_module, "create_chat_model", fake_create_chat_model)

        cls = get_middleware_registry().resolve("ScaffoldSummarizationMiddleware")
        instance = cls(model_name="fake-model", trigger=[("messages", 100)], keep=("messages", 10))

        assert len(calls) == 1
        assert calls[0].name == "fake-model"
        assert instance.model is fake_model
