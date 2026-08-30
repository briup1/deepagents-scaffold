"""Mock chat model for development and end-to-end verification.

Avoids real LLM API calls by returning deterministic responses. Registered via
``use: scaffold.infra.models.mock:MockChatModel`` in ``config.yaml``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr


class MockChatModel(BaseChatModel):
    """返回固定文本的 mock 聊天模型。

    Args:
        model: 必填字段，与配置中的 ``model`` 对应，仅用于标识。
        response_text: 每次调用返回的固定文本。
        sleep_ms: 流式输出时相邻 chunk 之间的模拟延迟（毫秒）。
    """

    model: str = "mock"
    response_text: str = "你好！我是 DeepAgents Scaffold 的默认助手。很高兴为你服务。"
    sleep_ms: float = 30.0
    echo_user_messages: bool = False
    _tools_bound: bool = PrivateAttr(default=False)

    def _response_content(self, messages: list[BaseMessage]) -> str:
        """返回本次调用的响应文本。"""
        if self.echo_user_messages:
            user_contents = [str(m.content) for m in messages if isinstance(m, HumanMessage)]
            if user_contents:
                return "Echo: " + " | ".join(user_contents)
        return self.response_text

    @property
    def _llm_type(self) -> str:
        return "mock_chat_model"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(content=self._response_content(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        text = self._response_content(messages)
        chunk_size = 4
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        text = self._response_content(messages)
        chunk_size = 4
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            if self.sleep_ms > 0:
                await asyncio.sleep(self.sleep_ms / 1000.0)
            yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))

    def bind_tools(self, tools: Any, **kwargs: Any) -> "MockChatModel":
        """模拟工具绑定，返回自身以兼容需要 bind_tools 的 agent 构建流程。"""
        self._tools_bound = True
        return self
