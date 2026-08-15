"""中间件可观测性包装器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage

from scaffold.infra.middleware.telemetry import (
    StateTelemetryWrapper,
    summarize_model_request,
    summarize_state,
    summarize_tool_request,
    summarize_update,
)


class FakeBeforeModelMiddleware(AgentMiddleware):
    """只覆盖 before_model 的假中间件。"""

    def before_model(self, state, runtime):
        return {"_test_key": "changed", "messages": [AIMessage(content="hi")]}


class FakeWrapModelMiddleware(AgentMiddleware):
    """覆盖 wrap_model_call 的假中间件。"""

    def wrap_model_call(self, request, handler):
        modified = request.override(system_message=MagicMock(text="modified"))
        return handler(modified)


class FakeNoopMiddleware(AgentMiddleware):
    """未覆盖任何 hook 的假中间件。"""


class TestSummarizeState:
    def test_summarizes_messages_and_other_keys(self):
        state = {
            "messages": [HumanMessage(content="hello"), AIMessage(content="world")],
            "_token_usage_total": 123,
            "_loop_counts": {"read_file": 3},
        }
        summary = summarize_state(state)

        assert summary["type"] == "dict"
        assert summary["messages_count"] == 2
        assert summary["last_message"]["role"] == "ai"
        assert summary["last_message"]["content_length"] == 5
        assert summary["other_keys"]["_token_usage_total"]["value"] == 123
        assert summary["other_keys"]["_loop_counts"]["len"] == 1

    def test_handles_non_dict_state(self):
        summary = summarize_state(None)
        assert summary["type"] == "None"


class TestSummarizeUpdate:
    def test_summarizes_message_delta(self):
        update = {
            "messages": [AIMessage(content="hi")],
            "_test_key": "changed",
        }
        summary = summarize_update(update)

        assert summary["keys"] == ["messages", "_test_key"]
        assert summary["messages_delta_count"] == 1
        assert summary["last_delta_message"]["role"] == "ai"
        assert summary["other_keys"]["_test_key"]["preview"] == "changed"

    def test_returns_none_for_none_update(self):
        assert summarize_update(None) is None


class TestSummarizeModelRequest:
    def test_summarizes_request(self):
        request = MagicMock()
        request.state = {"messages": [HumanMessage(content="hello")]}
        request.system_message = None
        request.messages = []
        request.tools = []

        summary = summarize_model_request(request)
        assert summary["type"] == "MagicMock"
        assert summary["state"]["messages_count"] == 1
        assert summary["system_message"] == {"type": "None"}


class TestSummarizeToolRequest:
    def test_summarizes_tool_call_dict(self):
        request = MagicMock()
        request.tool_call = {"name": "read_file", "id": "call-1"}
        request.state = {"messages": []}

        summary = summarize_tool_request(request)
        assert summary["tool_name"] == "read_file"
        assert summary["tool_call_id"] == "call-1"


class TestStateTelemetryWrapper:
    def test_wraps_before_model_and_logs_exit(self):
        wrapped = FakeBeforeModelMiddleware()
        wrapper = StateTelemetryWrapper(wrapped, index=2)

        state = {"messages": [HumanMessage(content="hello")]}
        runtime = MagicMock()

        with (
            patch.object(wrapper._logger, "debug"),
            patch.object(wrapper._logger, "info") as mock_info,
        ):
            result = wrapper.before_model(state, runtime)

        assert result["_test_key"] == "changed"
        assert mock_info.called

        # 检查 exit 日志字段
        _, call_kwargs = mock_info.call_args
        extra = call_kwargs["extra"]
        assert extra["event"] == "middleware_hook_exit"
        assert extra["middleware"] == "FakeBeforeModelMiddleware"
        assert extra["hook"] == "before_model"
        assert extra["index"] == 2
        assert extra["update_summary"]["other_keys"]["_test_key"]["preview"] == "changed"

    def test_wraps_wrap_model_call_and_captures_modified_request(self):
        wrapped = FakeWrapModelMiddleware()
        wrapper = StateTelemetryWrapper(wrapped, index=0)

        request = MagicMock()
        request.state = {"messages": []}
        request.system_message = None
        request.messages = []
        request.tools = []
        modified_request = MagicMock()
        modified_request.state = {"messages": []}
        modified_request.system_message = MagicMock(text="modified")
        modified_request.messages = []
        modified_request.tools = []
        request.override.return_value = modified_request

        response = MagicMock()
        response.result = [MagicMock()]
        response.result[0].role = "ai"
        response.result[0].content = "ok"
        response.result[0].tool_calls = None
        response.structured_response = None
        handler = MagicMock(return_value=response)

        with (
            patch.object(wrapper._logger, "debug"),
            patch.object(wrapper._logger, "info") as mock_info,
        ):
            wrapper.wrap_model_call(request, handler)

        assert mock_info.called
        _, call_kwargs = mock_info.call_args
        extra = call_kwargs["extra"]
        assert extra["event"] == "middleware_model_call_exit"
        assert extra["middleware"] == "FakeWrapModelMiddleware"
        # 最终传给 handler 的 request 摘要应体现修改
        assert extra["request_summary"]["system_message"]["type"] == "MagicMock"

    def test_only_binds_overridden_wrap_hooks(self):
        """未覆盖 wrap_model_call 的中间件，包装后实例不应动态绑定 wrap_model_call。"""
        wrapped = FakeBeforeModelMiddleware()
        wrapper = StateTelemetryWrapper(wrapped, index=0)

        assert "before_model" in wrapper.__dict__
        assert "wrap_model_call" not in wrapper.__dict__
        assert "awrap_model_call" not in wrapper.__dict__

    def test_noop_middleware_still_logs_state_hooks(self):
        wrapped = FakeNoopMiddleware()
        wrapper = StateTelemetryWrapper(wrapped, index=0)

        with (
            patch.object(wrapper._logger, "debug"),
            patch.object(wrapper._logger, "info") as mock_info,
        ):
            wrapper.before_model({"messages": []}, MagicMock())

        assert mock_info.called

    def test_name_tools_state_schema_pass_through(self):
        wrapped = FakeBeforeModelMiddleware()
        wrapped.state_schema = {"custom": "schema"}
        wrapped.tools = ["tool-a"]
        wrapped.transformers = ("tf-a",)

        wrapper = StateTelemetryWrapper(wrapped, index=0)
        assert wrapper.name == "FakeBeforeModelMiddleware"
        assert wrapper.state_schema == {"custom": "schema"}
        assert wrapper.tools == ["tool-a"]
        assert wrapper.transformers == ("tf-a",)
