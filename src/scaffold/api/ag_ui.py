"""ag-ui 集成：将已注册的 DeepAgents graph 托管为 /agent SSE 端点。"""

from __future__ import annotations

import logging
from typing import Any

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

from scaffold.core.agents import get_agent, list_agents

logger = logging.getLogger(__name__)


def _build_ag_ui_agent(name: str) -> LangGraphAgent:
    """包装已编译的 DeepAgents graph 为 ag-ui LangGraphAgent。"""
    graph = get_agent(name)
    return LangGraphAgent(name=name, graph=graph)


def register_ag_ui_endpoints(app: Any) -> None:
    """为每个已注册 agent 在 FastAPI app 上注册 ag-ui 端点。"""
    agents = list_agents()
    if not agents:
        logger.warning("No agents registered; skipping ag-ui endpoint registration")
        return

    for info in agents:
        name = info["name"]
        path = f"/agent/{name}" if len(agents) > 1 else "/agent"
        agent = _build_ag_ui_agent(name)
        add_langgraph_fastapi_endpoint(app, agent, path)
        logger.info("AG-UI endpoint registered: %s -> agent=%s", path, name)
