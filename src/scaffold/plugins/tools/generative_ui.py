"""Generative UI 渲染工具。

Agent 通过调用 `render_ui` 告诉前端渲染哪个组件、传递什么 props；
前端使用 `useRenderTool("render_ui")` 捕获工具结果并渲染。
"""

from __future__ import annotations


async def render_ui(
    type: str,
    props: dict | None = None,
    surface_id: str | None = None,
) -> dict:
    """渲染前端组件。

    Args:
        type: 组件名，前端 Catalog 中已注册，例如 markdown_card、data_table、form 等。
        props: 组件属性，由对应组件的 schema 决定。
        surface_id: 可选表面 ID，用于更新同一界面区域而非创建新组件。

    Returns:
        包含 generative_ui 信封的字典，前端据此渲染组件。
    """
    return {
        "generative_ui": {
            "type": type,
            "props": props or {},
            "surfaceId": surface_id,
        }
    }
