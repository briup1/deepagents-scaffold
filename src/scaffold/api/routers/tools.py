"""Tool listing API."""

from fastapi import APIRouter
from pydantic import BaseModel

from scaffold.core.tools import get_available_tools

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    description: str | None


class ToolsListResponse(BaseModel):
    tools: list[ToolInfo]


@router.get("/", response_model=ToolsListResponse)
async def list_tools() -> ToolsListResponse:
    """List all available tools."""
    tools = get_available_tools()
    return ToolsListResponse(tools=[ToolInfo(name=t.name, description=t.description) for t in tools])
