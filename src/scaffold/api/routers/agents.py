"""Agent listing API."""

from fastapi import APIRouter
from pydantic import BaseModel

from scaffold.core.agents import list_agents

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentsListResponse(BaseModel):
    agents: list[dict]


@router.get("/", response_model=AgentsListResponse)
async def list_registered_agents() -> AgentsListResponse:
    """List all registered agents."""
    return AgentsListResponse(agents=list_agents())
