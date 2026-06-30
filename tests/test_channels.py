"""Tests for the channel adapter framework."""

from __future__ import annotations


from scaffold.infra.channels.registry import get_channel_registry
from scaffold.infra.channels.router import ChannelRouter


class TestChannelRegistry:
    def test_resolve_slack(self):
        registry = get_channel_registry()
        cls = registry.resolve("slack")
        assert cls.__name__ == "SlackChannel"

    def test_list_known(self):
        registry = get_channel_registry()
        names = registry.list_known()
        assert "slack" in names


class TestChannelRouter:
    def test_init(self):
        router = ChannelRouter()
        assert router.app_config is not None
