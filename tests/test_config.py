"""Tests for the configuration system."""

from __future__ import annotations


from scaffold.infra.config.app_config import AppConfig
from scaffold.infra.config.backend_config import BackendConfig
from scaffold.infra.config.middleware_config import MiddlewareChainConfig, MiddlewareConfig
from scaffold.infra.config.profile_config import HarnessProfileConfig, ProfilesConfig


class TestAppConfig:
    def test_default_config(self):
        config = AppConfig()
        assert config.config_version == 1
        assert config.log_level == "info"
        assert config.models == []
        assert config.tools == []

    def test_hot_reload(self, tmp_path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("config_version: 42\nlog_level: debug\n")

        config = AppConfig.from_file(str(yaml_path))
        assert config.config_version == 42
        assert config.log_level == "debug"

    def test_middleware_config(self):
        config = AppConfig()
        assert isinstance(config.middleware, MiddlewareChainConfig)
        assert config.middleware.items == []

    def test_backend_config(self):
        config = AppConfig()
        assert isinstance(config.backend, BackendConfig)
        assert config.backend.type == "filesystem"

    def test_profile_config(self):
        config = AppConfig()
        assert isinstance(config.profiles, ProfilesConfig)
        assert config.profiles.harness == []

    def test_env_variable_resolution(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TEST_API_KEY", "secret123")
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            "models:\n"
            "  - name: test\n"
            "    display_name: Test\n"
            "    use: langchain_openai:ChatOpenAI\n"
            "    model: gpt-4\n"
            "    api_key: $TEST_API_KEY\n"
        )

        config = AppConfig.from_file(str(yaml_path))
        assert config.models[0].api_key == "secret123"


class TestMiddlewareConfig:
    def test_middleware_item(self):
        item = MiddlewareConfig(name="LoopDetectionMiddleware", enabled=True, kwargs={"warn_threshold": 2})
        assert item.name == "LoopDetectionMiddleware"
        assert item.enabled is True

    def test_get_enabled(self):
        chain = MiddlewareChainConfig(
            items=[
                MiddlewareConfig(name="A", enabled=True),
                MiddlewareConfig(name="B", enabled=False),
                MiddlewareConfig(name="C", enabled=True),
            ]
        )
        enabled = chain.get_enabled()
        assert len(enabled) == 2
        assert enabled[0].name == "A"
        assert enabled[1].name == "C"


class TestProfileConfig:
    def test_harness_profile(self):
        profile = HarnessProfileConfig(
            name="test",
            base_system_prompt="Custom base",
            system_prompt_suffix="Custom suffix",
        )
        assert profile.name == "test"
        assert profile.base_system_prompt == "Custom base"
