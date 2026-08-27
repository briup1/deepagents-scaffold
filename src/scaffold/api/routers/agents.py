"""Agent 列表与管理 API。"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from scaffold.api.deps import get_checkpointer, get_history_repo
from scaffold.runtime.agents import list_agents

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentsListResponse(BaseModel):
    agents: list[dict]


class AgentThreadsDeleteResponse(BaseModel):
    agent_id: str
    deleted_count: int
    deleted_thread_ids: list[str]


@router.get("/", response_model=AgentsListResponse)
async def list_registered_agents() -> AgentsListResponse:
    """列出所有已注册的 agent。"""
    return AgentsListResponse(agents=list_agents())


@router.delete("/{agent_id}/threads", response_model=AgentThreadsDeleteResponse)
async def delete_agent_threads(agent_id: str, request: Request) -> AgentThreadsDeleteResponse:
    """清空指定 Agent 的全部会话（历史消息 + checkpoint 状态）。"""
    history_repo = get_history_repo(request)
    checkpointer = get_checkpointer(request)

    thread_ids = await history_repo.delete_threads_by_agent(agent_id)
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)
    return AgentThreadsDeleteResponse(
        agent_id=agent_id,
        deleted_count=len(thread_ids),
        deleted_thread_ids=thread_ids,
    )
