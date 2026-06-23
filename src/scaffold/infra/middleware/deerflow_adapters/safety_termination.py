"""Safety termination middleware.

Detects provider safety refusals (content_filter, refusal, SAFETY)
and strips truncated tool_calls before execution.

Adapted from deerflow.agents.middlewares.safety_finish_reason_middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Known provider safety signals
_SAFETY_SIGNALS = {
    "content_filter",
    "refusal",
    "SAFETY",
    "safety",
    "blocked",
    "ResponsibleAIPolicyViolation",
}


class SafetyTerminationMiddleware(AgentMiddleware):
    """Detect safety terminations and handle gracefully.

    Args:
        strip_truncated_tool_calls: Remove incomplete tool_calls from blocked responses.
        emit_warning: Inject a warning system message when safety block detected.
    """

    def __init__(
        self,
        *,
        strip_truncated_tool_calls: bool = True,
        emit_warning: bool = True,
    ) -> None:
        self.strip_truncated_tool_calls = strip_truncated_tool_calls
        self.emit_warning = emit_warning

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Check last message for safety signals."""
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        # Check response_metadata for safety signals
        metadata = getattr(last_msg, "response_metadata", {}) or {}
        finish_reason = metadata.get("finish_reason", "")
        model_name = metadata.get("model_name", "")

        # Also check content for refusal patterns
        content = str(last_msg.content or "")
        is_safety = (
            finish_reason in _SAFETY_SIGNALS
            or any(sig in content.lower() for sig in _SAFETY_SIGNALS)
            or "i cannot" in content.lower()
            and "policy" in content.lower()
        )

        if not is_safety:
            return None

        logger.warning("Safety termination detected: finish_reason=%s model=%s", finish_reason, model_name)

        updates: dict[str, Any] = {}

        # Strip truncated tool calls
        if self.strip_truncated_tool_calls and hasattr(last_msg, "tool_calls"):
            tool_calls = last_msg.tool_calls
            if tool_calls:
                # Remove tool_calls from the message to prevent execution
                stripped_msg = AIMessage(content=last_msg.content)
                messages[-1] = stripped_msg
                updates["messages"] = messages
                logger.debug("Stripped %d tool_calls from safety-blocked response", len(tool_calls))

        # Emit warning
        if self.emit_warning:
            warning = SystemMessage(
                content="WARNING: The previous response was blocked by a safety filter. "
                "Avoid generating harmful content. If this was a mistake, rephrase your request."
            )
            updates["messages"] = [*messages, warning]

        return updates

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Async variant."""
        return self.after_model(state, runtime)
