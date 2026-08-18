"""标题生成中间件。

在第一条用户消息后，通过轻量级 LLM 调用自动生成会话标题。

改编自 deerflow.agents.middlewares.title_middleware。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# 模块级标题缓存，供 AG-UI endpoint 在 RUN_FINISHED 时读取并持久化。
_thread_titles: dict[str, str] = {}


def get_thread_title(thread_id: str) -> str | None:
    """获取指定线程由 TitleMiddleware 生成的标题。"""
    return _thread_titles.get(thread_id)


class TitleMiddleware(AgentMiddleware):
    """在第一条用户消息后生成线程标题。

    Args:
        max_title_length: 生成标题的最大长度。
        model_name: 用于标题生成的可选模型名称（为 None 时使用默认模型）。
    """

    def __init__(
        self,
        *,
        max_title_length: int = 60,
        model_name: str | None = None,
    ) -> None:
        self.max_title_length = max_title_length
        self.model_name = model_name
        self._generated: set[str] = set()

    def after_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """在首次助手响应后生成标题。"""
        config = get_config()
        thread_id = config.get("configurable", {}).get("thread_id", "default") if config else "default"

        if thread_id in self._generated:
            return None

        messages = state.get("messages", [])
        if len(messages) < 2:
            return None

        # 查找第一条用户消息
        user_messages = [m for m in messages if getattr(m, "type", None) == "human"]
        if not user_messages:
            return None

        first_user_text = str(getattr(user_messages[0], "content", ""))[:200]
        if not first_user_text:
            return None

        # 简单启发式标题生成（生产环境应使用 LLM）
        title = _generate_title_heuristic(first_user_text, self.max_title_length)
        self._generated.add(thread_id)
        _thread_titles[thread_id] = title

        logger.info("Generated title for thread %s: %s", thread_id, title)

        return {"_thread_title": title}

    async def aafter_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """异步变体。"""
        return self.after_model(state, runtime)


def _generate_title_heuristic(text: str, max_length: int) -> str:
    """从第一条用户消息生成简洁标题。

    生产环境中应调用轻量级 LLM 以获得更好质量。
    """
    # 取第一句或前 N 个词
    first_sentence = text.split(".")[0].split("\n")[0]
    words = first_sentence.split()[:8]
    title = " ".join(words)

    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return title or "New Conversation"
