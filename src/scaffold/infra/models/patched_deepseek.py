"""Patched ChatDeepSeek that preserves reasoning_content in multi-turn conversations.

Adapted from deerflow.models.patched_deepseek.

When using thinking/reasoning enabled models, the DeepSeek API expects
reasoning_content to be present on ALL assistant messages in multi-turn
conversations. The original langchain-deepseek implementation stores
reasoning_content in additional_kwargs but doesn't include it when making
subsequent API calls, which causes errors with APIs that require it.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek


class PatchedChatDeepSeek(ChatDeepSeek):
    """ChatDeepSeek with proper reasoning_content preservation."""

    @classmethod
    def is_lc_serializable(cls) -> bool:
        return True

    @property
    def lc_secrets(self) -> dict[str, str]:
        return {"api_key": "DEEPSEEK_API_KEY", "openai_api_key": "DEEPSEEK_API_KEY"}

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Get request payload with reasoning_content preserved."""
        original_messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages", [])

        if len(payload_messages) == len(original_messages):
            for payload_msg, orig_msg in zip(payload_messages, original_messages):
                if payload_msg.get("role") == "assistant" and isinstance(orig_msg, AIMessage):
                    reasoning_content = orig_msg.additional_kwargs.get("reasoning_content")
                    if reasoning_content is not None:
                        payload_msg["reasoning_content"] = reasoning_content
        else:
            ai_messages = [m for m in original_messages if isinstance(m, AIMessage)]
            assistant_payloads = [(i, m) for i, m in enumerate(payload_messages) if m.get("role") == "assistant"]
            for (idx, payload_msg), ai_msg in zip(assistant_payloads, ai_messages):
                reasoning_content = ai_msg.additional_kwargs.get("reasoning_content")
                if reasoning_content is not None:
                    payload_messages[idx]["reasoning_content"] = reasoning_content

        return payload
