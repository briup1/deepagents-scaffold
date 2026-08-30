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

    def test_default_memory_config(self):
        config = AppConfig()
        assert config.memory.enabled is True
        assert config.memory.storage_path == "./data/AGENTS.md"

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


class TestAuthConfig:
    def test_default_disabled(self):
        config = AppConfig()
        assert config.auth.enabled is False
        assert config.auth.users == []
        assert config.auth.token_user_map() == {}

    def test_token_user_map(self):
        config = AppConfig.model_validate(
            {
                "auth": {
                    "enabled": True,
                    "users": [
                        {"user_id": "alice", "token": "ta"},
                        {"user_id": "bob", "token": "tb"},
                    ],
                }
            }
        )
        assert config.auth.token_user_map() == {"ta": "alice", "tb": "bob"}

    def test_enabled_empty_token_raises(self):
        import pytest

        with pytest.raises(ValueError, match="empty token"):
            AppConfig.model_validate(
                {"auth": {"enabled": True, "users": [{"user_id": "alice", "token": ""}]}}
            )

    def test_enabled_duplicate_token_raises(self):
        import pytest

        with pytest.raises(ValueError, match="duplicate token"):
            AppConfig.model_validate(
                {
                    "auth": {
                        "enabled": True,
                        "users": [
                            {"user_id": "alice", "token": "same"},
                            {"user_id": "bob", "token": "same"},
                        ],
                    }
                }
            )

    def test_enabled_duplicate_user_id_raises(self):
        import pytest

        with pytest.raises(ValueError, match="duplicate user_id"):
            AppConfig.model_validate(
                {
                    "auth": {
                        "enabled": True,
                        "users": [
                            {"user_id": "alice", "token": "t1"},
                            {"user_id": "alice", "token": "t2"},
                        ],
                    }
                }
            )

    def test_missing_env_var_in_auth_path_raises_with_var_name(self, monkeypatch):
        import pytest

        monkeypatch.delenv("SCAFFOLD_TOKEN_MISSING", raising=False)
        with pytest.raises(ValueError, match="SCAFFOLD_TOKEN_MISSING"):
            AppConfig._resolve_env_variables(
                {"auth": {"enabled": True, "users": [{"user_id": "alice", "token": "$SCAFFOLD_TOKEN_MISSING"}]}}
            )

    def test_missing_env_var_outside_auth_falls_back_to_empty(self, monkeypatch):
        monkeypatch.delenv("SOME_MISSING_KEY", raising=False)
        resolved = AppConfig._resolve_env_variables({"models": [{"api_key": "$SOME_MISSING_KEY"}]})
        assert resolved["models"][0]["api_key"] == ""

    def test_auth_env_var_resolved(self, monkeypatch):
        monkeypatch.setenv("SCAFFOLD_TOKEN_X", "secret-x")
        resolved = AppConfig._resolve_env_variables(
            {"auth": {"users": [{"user_id": "alice", "token": "$SCAFFOLD_TOKEN_X"}]}}
        )
        assert resolved["auth"]["users"][0]["token"] == "secret-x"
