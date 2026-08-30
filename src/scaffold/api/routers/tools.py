"""工具列表 API。"""

from fastapi import APIRouter
from pydantic import BaseModel

from scaffold.infra.config.app_config import get_app_config

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    description: str | None


class ToolsListResponse(BaseModel):
    tools: list[ToolInfo]


@router.get("/", response_model=ToolsListResponse)
async def list_tools() -> ToolsListResponse:
    """列出所有可用工具。"""
    tools = get_app_config().tools
    return ToolsListResponse(tools=[ToolInfo(name=tool.name, description=tool.description) for tool in tools])
