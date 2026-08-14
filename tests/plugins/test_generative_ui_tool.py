"""Generative UI 工具单元测试。"""

from __future__ import annotations

import pytest

from scaffold.plugins.tools.generative_ui import render_ui


@pytest.mark.asyncio
async def test_render_ui_returns_envelope() -> None:
    result = await render_ui(
        type="markdown_card",
        props={"title": "Summary", "content": "Hello"},
        surface_id="surface-1",
    )
    assert result == {
        "generative_ui": {
            "type": "markdown_card",
            "props": {"title": "Summary", "content": "Hello"},
            "surfaceId": "surface-1",
        }
    }


@pytest.mark.asyncio
async def test_render_ui_defaults() -> None:
    result = await render_ui(type="metric_card", props={"value": 42})
    assert result["generative_ui"]["type"] == "metric_card"
    assert result["generative_ui"]["props"] == {"value": 42}
    assert result["generative_ui"]["surfaceId"] is None
