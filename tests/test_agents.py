"""Tests for scaffold.runtime.agents agent factory and registry."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from scaffold.infra.config.app_config import get_app_config
from scaffold.runtime.agents import _agent_registry, create_agent, get_agent, list_agents


@pytest.fixture(autouse=True)
def _clear_agent_registry() -> None:
    """每个测试前清空 agent 注册表，避免测试间互相污染。"""
    _agent_registry.clear()
    yield
    _agent_registry.clear()


class TestCreateAgent:
    def test_create_default_agent_uses_default_harness(self, _reset_app_config: Any) -> None:
        agent = create_agent(name="default")
        assert "default" in _agent_registry
        assert _agent_registry["default"] is agent

    def test_create_agent_with_harness_profile(self, _reset_app_config: Any) -> None:
        agent_default = create_agent(name="default", harness_profile="default")
        agent_coding = create_agent(name="coding", harness_profile="coding")

        assert agent_default is not agent_coding
        assert "default" in _agent_registry
        assert "coding" in _agent_registry

    def test_create_data_extractor_agent_excludes_dev_tools(self, _reset_app_config: Any) -> None:
        captured_tools: list[Any] = []

        def _fake_create_deep_agent(*, tools: list[Any], **kwargs: Any) -> Any:
            captured_tools.extend(tools)
            # 返回一个最小 mock，满足注册表与 get_agent 的基本期望
            mock_agent = type("MockCompiledGraph", (), {"name": "data_extractor"})()
            _agent_registry["data_extractor"] = mock_agent
            return mock_agent

        with patch("scaffold.runtime.agents._create_deep_agent", side_effect=_fake_create_deep_agent):
            create_agent(name="data_extractor", harness_profile="data_extractor")

        assert "data_extractor" in _agent_registry
        tool_names = {getattr(t, "name", None) for t in captured_tools}
        assert "read_file" not in tool_names
        assert "write_file" not in tool_names
        assert "preview_excel" in tool_names
        assert "generate_extraction_code" in tool_names
        assert "execute_extraction_code" in tool_names
        assert "validate_extraction_result" in tool_names

    def test_create_agent_overwrites_same_name(self, _reset_app_config: Any) -> None:
        first = create_agent(name="default", harness_profile="default")
        second = create_agent(name="default", harness_profile="coding")

        assert "default" in _agent_registry
        assert _agent_registry["default"] is second
        assert _agent_registry["default"] is not first

    def test_create_agent_unknown_harness_falls_back_to_default(self, _reset_app_config: Any) -> None:
        app_config = get_app_config()
        agent = create_agent(name="default", harness_profile="nonexistent")

        assert "default" in _agent_registry
        assert _agent_registry["default"] is agent
        # 未知 profile 应回退到 default_harness，并用其提示词构建
        assert app_config.profiles.default_harness in ("default", "code_reviewer")


class TestGetAgent:
    def test_get_agent_returns_created_agent(self, _reset_app_config: Any) -> None:
        created = create_agent(name="coding")
        fetched = get_agent("coding")
        assert fetched is created

    def test_get_agent_defaults_to_default_name(self, _reset_app_config: Any) -> None:
        created = create_agent(name="default")
        fetched = get_agent()
        assert fetched is created

    def test_get_agent_raises_for_missing_name(self, _reset_app_config: Any) -> None:
        create_agent(name="default")
        with pytest.raises(KeyError):
            get_agent("nonexistent")


class TestListAgents:
    def test_list_agents_returns_all_names(self, _reset_app_config: Any) -> None:
        create_agent(name="default")
        create_agent(name="coding")
        create_agent(name="code_reviewer")

        agents = list_agents()
        names = {a["name"] for a in agents}
        assert names == {"default", "coding", "code_reviewer"}
