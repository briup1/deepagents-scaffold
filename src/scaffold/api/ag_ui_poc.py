"""ag-ui 集成 PoC：将 default agent 的 graph 托管为 /agent 端点。"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.core.agents import get_agent

logger = logging.getLogger(__name__)


def _build_ag_ui_agent() -> Any:
    """包装已编译的 DeepAgents graph 为 ag-ui LangGraphAgent。"""
    from ag_ui_langgraph import LangGraphAgent

    graph = get_agent("default")
    return LangGraphAgent(name="default", graph=graph)


def register_ag_ui_endpoint(app: Any) -> None:
    """在 FastAPI app 上注册 ag-ui /agent 端点。"""
    from ag_ui_langgraph import add_langgraph_fastapi_endpoint

    agent = _build_ag_ui_agent()
    add_langgraph_fastapi_endpoint(app, agent, "/agent")
    logger.info("AG-UI /agent endpoint registered")
