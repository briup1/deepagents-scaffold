"""Tests for DeepAgentsSummarizationMiddleware adapter."""

from __future__ import annotations

from scaffold.infra.middleware.deerflow_adapters.deepagents_summarization import (
    DeepAgentsSummarizationMiddleware,
)
from scaffold.infra.middleware.registry import get_middleware_registry


class _FakeAppConfig:
    class _ModelConfig:
        name = "fake-model"
        use = "fake:FakeModel"
        model = "fake"

    class _BackendConfig:
        type = "filesystem"

        class filesystem:
            root_dir = "/"

    models = [_ModelConfig()]
    backend = _BackendConfig()

    @classmethod
    def get_model_config(cls, name):
        return cls._ModelConfig() if name == "fake-model" else None


class TestDeepAgentsSummarizationMiddleware:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("DeepAgentsSummarizationMiddleware")
        assert cls.__name__ == "DeepAgentsSummarizationMiddleware"

    def _patch_adapter_deps(self, monkeypatch, fake_model):
        import scaffold.infra.config.app_config as app_config_module
        import scaffold.infra.middleware.deerflow_adapters.deepagents_summarization as adapter_module

        monkeypatch.setattr(app_config_module, "get_app_config", lambda config_path=None: _FakeAppConfig())
        monkeypatch.setattr(adapter_module, "create_chat_model", lambda cfg, **kwargs: fake_model)
        monkeypatch.setattr(
            adapter_module,
            "compute_summarization_defaults",
            lambda model: {
                "trigger": ("messages", 10),
                "keep": ("messages", 2),
                "truncate_args_settings": None,
            },
        )

    def test_default_params(self, monkeypatch):
        fake_model = type("FakeModel", (), {"_llm_type": "fake", "profile": None})()
        self._patch_adapter_deps(monkeypatch, fake_model)

        mw = DeepAgentsSummarizationMiddleware()

        assert mw._lc_helper.model is fake_model
        assert mw._lc_helper.trigger == ("messages", 10)
        assert mw._lc_helper.keep == ("messages", 2)

    def test_custom_summary_prompt_and_trim(self, monkeypatch):
        fake_model = type("FakeModel", (), {"_llm_type": "fake", "profile": None})()
        self._patch_adapter_deps(monkeypatch, fake_model)

        mw = DeepAgentsSummarizationMiddleware(
            summary_prompt="Custom prompt: {messages}",
            trim_tokens_to_summarize=1234,
        )

        assert mw._lc_helper.summary_prompt == "Custom prompt: {messages}"
        assert mw._lc_helper.trim_tokens_to_summarize == 1234

    def test_name_is_distinct_from_default(self, monkeypatch):
        fake_model = type("FakeModel", (), {"_llm_type": "fake", "profile": None})()
        self._patch_adapter_deps(monkeypatch, fake_model)

        mw = DeepAgentsSummarizationMiddleware()
        assert mw.name == "DeepAgentsSummarizationMiddleware"

    def test_custom_trigger_and_keep(self, monkeypatch):
        fake_model = type("FakeModel", (), {"_llm_type": "fake", "profile": None})()
        self._patch_adapter_deps(monkeypatch, fake_model)

        mw = DeepAgentsSummarizationMiddleware(
            trigger=["messages", 30],
            keep=["messages", 5],
        )

        assert mw._lc_helper.trigger == ("messages", 30)
        assert mw._lc_helper.keep == ("messages", 5)
