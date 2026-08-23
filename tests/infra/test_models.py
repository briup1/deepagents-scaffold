"""模型工厂与模型适配器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.models.factory import create_chat_model
from scaffold.infra.models.patched_deepseek import PatchedChatDeepSeek, _fix_message_order


@pytest.fixture
def openai_config() -> ModelConfig:
    return ModelConfig(
        name="test-openai",
        display_name="Test OpenAI",
        use="langchain_openai:ChatOpenAI",
        api_key="sk-test",
        model="gpt-4",
    )


def test_bypass_proxy_injects_proxy_free_clients(openai_config: ModelConfig) -> None:
    openai_config.bypass_proxy = True

    with (
        patch("scaffold.infra.models.factory.httpx.Client") as mock_sync,
        patch("scaffold.infra.models.factory.httpx.AsyncClient") as mock_async,
    ):
        mock_sync_instance = MagicMock()
        mock_async_instance = MagicMock()
        mock_sync.return_value = mock_sync_instance
        mock_async.return_value = mock_async_instance

        with patch("scaffold.infra.models.factory._import_class") as mock_import:
            mock_cls = MagicMock()
            mock_cls.model_fields = {"http_client": MagicMock(), "http_async_client": MagicMock()}
            mock_import.return_value = mock_cls

            create_chat_model(openai_config)

            mock_sync.assert_called_once_with(proxy=None)
            mock_async.assert_called_once_with(proxy=None)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["http_client"] is mock_sync_instance
            assert call_kwargs["http_async_client"] is mock_async_instance


def test_bypass_proxy_warns_for_unsupported_provider(openai_config: ModelConfig, caplog) -> None:
    openai_config.bypass_proxy = True

    with patch("scaffold.infra.models.factory._import_class") as mock_import:
        mock_cls = MagicMock()
        # Provider does not expose http_client / http_async_client
        mock_cls.model_fields = {"model": MagicMock()}
        mock_import.return_value = mock_cls

        create_chat_model(openai_config)

        assert "does not support custom http_client/http_async_client" in caplog.text
        call_kwargs = mock_cls.call_args.kwargs
        assert "http_client" not in call_kwargs
        assert "http_async_client" not in call_kwargs


def test_no_bypass_proxy_does_not_inject_clients(openai_config: ModelConfig) -> None:
    openai_config.bypass_proxy = False

    with (
        patch("scaffold.infra.models.factory.httpx.Client") as mock_sync,
        patch("scaffold.infra.models.factory.httpx.AsyncClient") as mock_async,
        patch("scaffold.infra.models.factory._import_class") as mock_import,
    ):
        mock_cls = MagicMock()
        mock_cls.model_fields = {"http_client": MagicMock(), "http_async_client": MagicMock()}
        mock_import.return_value = mock_cls

        create_chat_model(openai_config)

        mock_sync.assert_not_called()
        mock_async.assert_not_called()
        call_kwargs = mock_cls.call_args.kwargs
        assert "http_client" not in call_kwargs
        assert "http_async_client" not in call_kwargs


def test_fix_message_order_moves_tool_messages_after_assistant_calls() -> None:
    """ToolMessage 被拖到后面时，应恢复到所属 AIMessage 之后。"""
    assistant_render = AIMessage(
        content="",
        id="ai-render",
        tool_calls=[{"id": "call_render", "name": "render_ui", "args": {}}],
    )
    assistant_summary = AIMessage(content="summary", id="ai-summary")
    assistant_read = AIMessage(
        content="",
        id="ai-read",
        tool_calls=[{"id": "call_read", "name": "read_file", "args": {}}],
    )
    tool_read = ToolMessage(content="file content", tool_call_id="call_read")
    tool_render = ToolMessage(content='{"generative_ui":{}}', tool_call_id="call_render")

    messy = [assistant_render, assistant_summary, assistant_read, tool_read, tool_render]
    fixed = _fix_message_order(messy)

    roles = [m.type for m in fixed]
    assert roles == ["ai", "tool", "ai", "ai", "tool"]
    assert fixed[1].tool_call_id == "call_render"  # type: ignore[union-attr]
    assert fixed[4].tool_call_id == "call_read"  # type: ignore[union-attr]


def test_fix_message_order_preserves_already_valid_order() -> None:
    """原本合法的顺序不应被改乱。"""
    assistant = AIMessage(
        content="",
        tool_calls=[{"id": "call_1", "name": "render_ui", "args": {}}],
    )
    tool = ToolMessage(content="ok", tool_call_id="call_1")
    user = HumanMessage(content="hello")

    fixed = _fix_message_order([user, assistant, tool])
    assert [m.type for m in fixed] == ["human", "ai", "tool"]


def test_fix_message_order_keeps_unmatched_tool_at_end() -> None:
    """找不到对应 assistant 的 tool 消息应被放到末尾，避免丢失。"""
    user = HumanMessage(content="hi")
    orphan = ToolMessage(content="orphan", tool_call_id="call_orphan")

    fixed = _fix_message_order([user, orphan])
    assert [m.type for m in fixed] == ["human", "tool"]


def test_patched_deepseek_request_payload_reorders_messages() -> None:
    """_get_request_payload 在序列化前会重排消息顺序。"""
    assistant_render = AIMessage(
        content="",
        tool_calls=[{"id": "call_render", "name": "render_ui", "args": {}}],
    )
    assistant_summary = AIMessage(content="summary")
    assistant_read = AIMessage(
        content="",
        tool_calls=[{"id": "call_read", "name": "read_file", "args": {}}],
    )
    tool_read = ToolMessage(content="file", tool_call_id="call_read")
    tool_render = ToolMessage(content='{"generative_ui":{}}', tool_call_id="call_render")

    model = PatchedChatDeepSeek(api_key="sk-test", model="deepseek-v4-flash")
    payload = model._get_request_payload([assistant_render, assistant_summary, assistant_read, tool_read, tool_render])
    payload_messages = payload["messages"]

    assert [m["role"] for m in payload_messages] == ["assistant", "tool", "assistant", "assistant", "tool"]
    assert payload_messages[1]["tool_call_id"] == "call_render"
    assert payload_messages[4]["tool_call_id"] == "call_read"
