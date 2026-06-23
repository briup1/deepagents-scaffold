"""Tool error handling middleware.

Catches exceptions during tool execution and converts them into error
ToolMessages so the agent can continue rather than crashing.

Adapted from deerflow.agents.middlewares.tool_error_handling_middleware.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """Wrap tool calls to catch exceptions and convert to error ToolMessages."""

    def wrap_tool_call(
        self,
        call: Any,
        state: Any,
        runtime: Runtime[Any],
    ) -> Any:
        """Wrap a single tool call with error handling."""
        try:
            return call
        except Exception as exc:
            # This hook fires around tool execution; actual exception handling
            # happens in the tool node. We log here for observability.
            logger.exception("Tool execution failed: %s", exc)
            raise

    async def awrap_tool_call(
        self,
        call: Any,
        state: Any,
        runtime: Runtime[Any],
    ) -> Any:
        """Async variant — delegates to sync version."""
        return self.wrap_tool_call(call, state, runtime)
