"""修复后的 ChatDeepSeek，在多轮对话中保留 reasoning_content。

从 deerflow.models.patched_deepseek 移植。

在使用 thinking/reasoning 模型时，DeepSeek API 要求
reasoning_content 出现在多轮对话的**所有** assistant 消息中。
原始 langchain-deepseek 实现将 reasoning_content 存放在 additional_kwargs 中，
但在后续 API 调用时不会将其包含进去，导致对需要该字段的 API 报错。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_deepseek import ChatDeepSeek

logger = logging.getLogger(__name__)


def _tool_call_id(tool_call: Any) -> str | None:
    """从 LangChain ToolCall dict 或对象中提取 tool_call_id。"""
    if isinstance(tool_call, dict):
        tool_call_id = tool_call.get("id")
    else:
        tool_call_id = getattr(tool_call, "id", None)
    return str(tool_call_id) if tool_call_id else None


def _fix_message_order(messages: list[Any]) -> list[Any]:
    """确保每条 assistant tool_calls 后面紧跟对应的 tool 结果消息。

    当 LangGraph 的摘要或记忆中间件截断/重排消息历史时，工具调用结果可能被拖到
    后续 assistant 消息甚至最新 user 消息之后。OpenAI/DeepSeek API 要求 tool_calls
    与 tool 消息严格交替，否则会报 ``insufficient tool messages following
    tool_calls message``。本函数先收集所有 ToolMessage，再把它们移动到所属
    AIMessage 之后，恢复合法顺序。
    """
    tool_messages: dict[str, ToolMessage] = {}
    ordered_messages: list[Any] = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_messages[msg.tool_call_id] = msg
        else:
            ordered_messages.append(msg)

    fixed: list[Any] = []
    used_tool_call_ids: set[str] = set()

    for msg in ordered_messages:
        fixed.append(msg)
        if not isinstance(msg, AIMessage) or not msg.tool_calls:
            continue

        for tool_call in msg.tool_calls:
            tool_call_id = _tool_call_id(tool_call)
            if not tool_call_id or tool_call_id in used_tool_call_ids:
                continue
            tool_msg = tool_messages.get(tool_call_id)
            if tool_msg is not None:
                fixed.append(tool_msg)
                used_tool_call_ids.add(tool_call_id)

    # 剩余的 tool 消息找不到对应 assistant（理论上不应发生），放在末尾兜底，避免丢数据。
    for tool_call_id, tool_msg in tool_messages.items():
        if tool_call_id not in used_tool_call_ids:
            fixed.append(tool_msg)

    return fixed


class PatchedChatDeepSeek(ChatDeepSeek):
    """正确保留 reasoning_content 的 ChatDeepSeek。"""

    @classmethod
    def is_lc_serializable(cls) -> bool:
        return True

    @property
    def lc_secrets(self) -> dict[str, str]:
        return {"api_key": "DEEPSEEK_API_KEY", "openai_api_key": "DEEPSEEK_API_KEY"}

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成，完成后记录 finish_reason 与内容长度供诊断。"""
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self._log_completion(result, streaming=False)
        return result

    async def _astream(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """异步流式生成，累计内容长度并在流结束时记录诊断信息。"""
        accumulated_content = ""
        accumulated_reasoning = ""
        finish_reason: str | None = None

        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            msg = chunk.message
            if isinstance(msg, AIMessageChunk):
                accumulated_content += msg.content if isinstance(msg.content, str) else ""
                accumulated_reasoning += msg.additional_kwargs.get("reasoning_content") or ""
                finish_reason = msg.response_metadata.get("finish_reason") or finish_reason
            yield chunk

        logger.info(
            "DeepSeek streaming finished | streaming=True finish_reason=%s content_len=%d reasoning_len=%d",
            finish_reason,
            len(accumulated_content),
            len(accumulated_reasoning),
        )

    def _log_completion(self, result: ChatResult, *, streaming: bool) -> None:
        """记录模型完成信息，用于判断回复是否因 token 限制被截断。"""
        if not result.generations:
            return
        gen = result.generations[0]
        msg = getattr(gen, "message", None)
        generation_info = getattr(gen, "generation_info", None) or {}
        finish_reason = generation_info.get("finish_reason")
        content = msg.content if isinstance(msg, AIMessage) and isinstance(msg.content, str) else ""
        reasoning = msg.additional_kwargs.get("reasoning_content") or "" if isinstance(msg, AIMessage) else ""
        logger.info(
            "DeepSeek completion finished | streaming=%s finish_reason=%s content_len=%d reasoning_len=%d",
            streaming,
            finish_reason,
            len(content),
            len(reasoning),
        )

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """获取请求 payload，同时保留 reasoning_content。"""
        original_messages = list(self._convert_input(input_).to_messages())
        fixed_messages = _fix_message_order(original_messages)
        payload = super()._get_request_payload(fixed_messages, stop=stop, **kwargs)
        payload_messages = payload.get("messages", [])

        # Diagnostic: log the message roles/ids/tool-call pairing right before
        # the request is sent to the DeepSeek API. This helps locate where a
        # dangling assistant tool_call loses its matching ToolMessage.
        try:
            logger.debug(
                "DeepSeek request messages | count=%d",
                len(payload_messages),
            )
            for i, msg in enumerate(payload_messages):
                tool_info: Any = None
                if msg.get("role") == "assistant":
                    tool_calls = msg.get("tool_calls") or []
                    tool_info = [tc.get("id") for tc in tool_calls]
                elif msg.get("role") == "tool":
                    tool_info = msg.get("tool_call_id")
                logger.debug(
                    "DeepSeek request message[%d] | role=%s id=%s tool_info=%s content_len=%s",
                    i,
                    msg.get("role"),
                    msg.get("id"),
                    tool_info,
                    len(msg.get("content", "")) if isinstance(msg.get("content"), (str, list)) else "?",
                )
        except Exception:
            logger.exception("Failed to log DeepSeek request messages")

        if len(payload_messages) == len(fixed_messages):
            for payload_msg, orig_msg in zip(payload_messages, fixed_messages):
                if payload_msg.get("role") == "assistant" and isinstance(orig_msg, AIMessage):
                    reasoning_content = orig_msg.additional_kwargs.get("reasoning_content")
                    if reasoning_content is not None:
                        payload_msg["reasoning_content"] = reasoning_content
        else:
            ai_messages = [m for m in fixed_messages if isinstance(m, AIMessage)]
            assistant_payloads = [(i, m) for i, m in enumerate(payload_messages) if m.get("role") == "assistant"]
            for (idx, payload_msg), ai_msg in zip(assistant_payloads, ai_messages):
                reasoning_content = ai_msg.additional_kwargs.get("reasoning_content")
                if reasoning_content is not None:
                    payload_messages[idx]["reasoning_content"] = reasoning_content

        return payload
