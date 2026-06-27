"""Token usage 追踪 middleware。

记录每次轮次的 token 消耗，并在整个会话中聚合。

改编自 deerflow.agents.middlewares.token_usage_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class TokenUsageMiddleware(AgentMiddleware):
    """追踪并记录每次模型调用的 token 用量。"""

    def __init__(
        self,
        *,
        log_interval: int = 1,
        aggregate: bool = True,
    ) -> None:
        self.log_interval = log_interval
        self.aggregate = aggregate
        self._call_count = 0

    def before_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """初始化 token 计数器。"""
        return {
            "_token_usage_total": 0,
            "_token_usage_prompt": 0,
            "_token_usage_completion": 0,
        }

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """从最后一条 AIMessage 中提取 token 用量。"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        usage = getattr(last_msg, "usage_metadata", None)
        if not usage:
            return None

        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        self._call_count += 1
        total = state.get("_token_usage_total", 0) + total_tokens
        prompt_total = state.get("_token_usage_prompt", 0) + prompt_tokens
        completion_total = state.get("_token_usage_completion", 0) + completion_tokens

        if self._call_count % self.log_interval == 0:
            logger.info(
                "Token usage — turn: %d prompt + %d completion = %d total | "
                "cumulative: %d prompt + %d completion = %d total",
                prompt_tokens,
                completion_tokens,
                total_tokens,
                prompt_total,
                completion_total,
                total,
            )

        return {
            "_token_usage_total": total,
            "_token_usage_prompt": prompt_total,
            "_token_usage_completion": completion_total,
        }

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步版本。"""
        return self.after_model(state, runtime)
