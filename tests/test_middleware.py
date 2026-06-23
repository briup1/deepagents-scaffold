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
