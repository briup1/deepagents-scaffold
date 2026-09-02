"""Tests for subagent configuration and builder."""

from __future__ import annotations

import pytest

from scaffold.infra.config.subagent_config import (
    PermissionRuleConfig,
    SubAgentDefinitionConfig,
    SubAgentsDefinitionsConfig,
)
from scaffold.core.subagents import _build_single_subagent
from scaffold.infra.config.app_config import AppConfig


class TestPermissionRuleConfig:
    def test_valid_permission_rule(self):
        rule = PermissionRuleConfig(
            paths=["/workspace/**"],
            operations=["read", "write"],
            mode="allow",
        )
        assert rule.paths == ["/workspace/**"]
        assert rule.operations == ["read", "write"]
        assert rule.mode == "allow"

    def test_default_mode(self):
        rule = PermissionRuleConfig(
            paths=["/workspace/**"],
            operations=["read"],
        )
        assert rule.mode == "allow"

    def test_missing_paths_raises(self):
        with pytest.raises(ValueError, match="Field required"):
            PermissionRuleConfig(operations=["read"])

    def test_missing_operations_raises(self):
        with pytest.raises(ValueError, match="Field required"):
            PermissionRuleConfig(paths=["/workspace/**"])

    def test_invalid_operation_raises(self):
        with pytest.raises(ValueError, match="Input should be"):
            PermissionRuleConfig(
                paths=["/workspace/**"],
                operations=["invalid"],
            )

    def test_path_must_start_with_slash(self):
        with pytest.raises(ValueError, match="Permission path must start with"):
            PermissionRuleConfig(
                paths=["workspace/**"],
                operations=["read"],
            )

    def test_path_no_double_dots(self):
        with pytest.raises(ValueError, match="must not contain"):
            PermissionRuleConfig(
                paths=["/workspace/../etc"],
                operations=["read"],
            )

    def test_path_no_tilde(self):
        with pytest.raises(ValueError, match="must start with"):
            PermissionRuleConfig(
                paths=["~/workspace"],
                operations=["read"],
            )


class TestSubAgentDefinitionConfig:
    def test_default_permissions_empty(self):
        cfg = SubAgentDefinitionConfig(
            name="test",
            description="Test agent",
            system_prompt="Prompt",
        )
        assert cfg.permissions == []

    def test_permissions_list_of_dicts(self):
        cfg = SubAgentDefinitionConfig(
            name="test",
            description="Test agent",
            system_prompt="Prompt",
            permissions=[
                {"paths": ["/workspace/**"], "operations": ["read", "write"]},
                {"paths": ["/secrets/**"], "operations": ["read"], "mode": "deny"},
            ],
        )
        assert len(cfg.permissions) == 2
        assert cfg.permissions[0].paths == ["/workspace/**"]
        assert cfg.permissions[0].operations == ["read", "write"]
        assert cfg.permissions[0].mode == "allow"
        assert cfg.permissions[1].mode == "deny"


class TestSubAgentsDefinitionsConfig:
    def test_get_enabled_filters(self):
        definitions = SubAgentsDefinitionsConfig(
            items=[
                SubAgentDefinitionConfig(name="a", description="A", system_prompt="p", enabled=True),
                SubAgentDefinitionConfig(name="b", description="B", system_prompt="p", enabled=False),
                SubAgentDefinitionConfig(name="c", description="C", system_prompt="p", enabled=True),
            ]
        )
        enabled = definitions.get_enabled()
        assert len(enabled) == 2
        assert enabled[0].name == "a"
        assert enabled[1].name == "c"


class TestBuildSingleSubagent:
    def test_build_subagent_with_permissions(self):
        cfg = SubAgentDefinitionConfig(
            name="test_agent",
            description="Test agent",
            system_prompt="You are a test agent",
            permissions=[
                {"paths": ["/workspace/**"], "operations": ["read", "write"], "mode": "allow"},
                {"paths": ["/etc/**"], "operations": ["read", "write"], "mode": "deny"},
            ],
        )
        app_config = AppConfig()

        subagent = _build_single_subagent(cfg, app_config)

        assert subagent is not None
        assert subagent["name"] == "test_agent"
        assert "permissions" in subagent
        assert len(subagent["permissions"]) == 2

        perm1 = subagent["permissions"][0]
        assert perm1.paths == ["/workspace/**"]
        assert perm1.operations == ["read", "write"]
        assert perm1.mode == "allow"

        perm2 = subagent["permissions"][1]
        assert perm2.paths == ["/etc/**"]
        assert perm2.operations == ["read", "write"]
        assert perm2.mode == "deny"

    def test_build_subagent_without_permissions(self):
        cfg = SubAgentDefinitionConfig(
            name="test_agent",
            description="Test agent",
            system_prompt="You are a test agent",
        )
        app_config = AppConfig()

        subagent = _build_single_subagent(cfg, app_config)

        assert subagent is not None
        assert "permissions" not in subagent or subagent.get("permissions") == []

    def test_build_subagent_invalid_permission_rejected_at_config_level(self):
        # Invalid permissions are caught at config validation level
        with pytest.raises(ValueError, match="must start with"):
            SubAgentDefinitionConfig(
                name="test_agent",
                description="Test agent",
                system_prompt="You are a test agent",
                permissions=[
                    {"paths": ["invalid_path"], "operations": ["read"]},
                ],
            )
