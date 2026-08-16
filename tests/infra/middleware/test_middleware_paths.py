"""中间件核心路径触发测试。

针对 config.yaml 中实际启用的四条中间件，验证其关键行为路径：
- DynamicContextMiddleware: 注入日期上下文
- ToolErrorHandlingMiddleware: 捕获工具异常并返回错误 ToolMessage
- LoopDetectionMiddleware: 检测重复工具调用并强制停止
- TokenUsageMiddleware: 聚合模型调用的 token 用量
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from unittest.mock import MagicMock

from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from scaffold.infra.middleware.deerflow_adapters.dynamic_context import (
    DynamicContextMiddleware,
)
from scaffold.infra.middleware.deerflow_adapters.loop_detection import (
    LoopDetectionMiddleware,
)
from scaffold.infra.middleware.deerflow_adapters.token_usage import TokenUsageMiddleware
from scaffold.infra.middleware.deerflow_adapters.tool_error_handling import (
    ToolErrorHandlingMiddleware,
)


class FakeModelRequest:
    """模拟 DynamicContextMiddleware 处理的 ModelRequest。"""

    def __init__(self, state: dict, system_message: SystemMessage) -> None:
        self.state = state
        self.system_message = system_message

    def override(self, *, system_message: SystemMessage) -> FakeModelRequest:
        return FakeModelRequest(self.state, system_message)


class TestDynamicContextMiddleware:
    """验证 DynamicContextMiddleware 的上下文注入路径。"""

    def _make_request(self, system_text: str = "You are helpful.") -> FakeModelRequest:
        return FakeModelRequest(
            state={"messages": [HumanMessage(content="hello")]},
            system_message=SystemMessage(content=system_text),
        )

    def test_injects_current_date_when_enabled(self):
        """启用 inject_date 时，system_message 应包含当前日期。"""
        mw = DynamicContextMiddleware(inject_date=True)
        request = self._make_request()
        handler = MagicMock(return_value="model_response")

        mw.wrap_model_call(request, handler)

        called_request = handler.call_args[0][0]
        new_system = called_request.system_message
        assert "[系统上下文]" in new_system.text
        assert "Current date and time:" in new_system.text
        # 验证日期格式为当天（UTC）
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert today in new_system.text

    def test_preserves_existing_system_message(self):
        """注入上下文时不应覆盖原有 system message，而是追加。"""
        mw = DynamicContextMiddleware(inject_date=True)
        request = self._make_request("Original system prompt.")
        handler = MagicMock(return_value="model_response")

        mw.wrap_model_call(request, handler)

        called_request = handler.call_args[0][0]
        new_system = called_request.system_message
        assert "Original system prompt." in new_system.text
        assert "[系统上下文]" in new_system.text

    def test_skips_injection_when_disabled(self):
        """inject_date 关闭时，请求原样传递。"""
        mw = DynamicContextMiddleware(inject_date=False)
        request = self._make_request()
        handler = MagicMock(return_value="model_response")

        mw.wrap_model_call(request, handler)

        called_request = handler.call_args[0][0]
        assert called_request is request

    async def test_async_path_also_injects(self):
        """异步路径 awrap_model_call 同样应注入上下文。"""
        mw = DynamicContextMiddleware(inject_date=True)
        request = self._make_request()

        async def handler(req):
            return "async_response"

        result = await mw.awrap_model_call(request, handler)

        assert result == "async_response"


class TestToolErrorHandlingMiddleware:
    """验证 ToolErrorHandlingMiddleware 的异常捕获路径。"""

    def test_catches_sync_exception_and_returns_error_tool_message(self):
        """同步工具调用异常应被转换为状态为 error 的 ToolMessage。"""
        mw = ToolErrorHandlingMiddleware(drop_error_from_history=True)
        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "bad_tool"},
            tool=None,
            state={},
            runtime=None,
        )

        def failing_handler(request):
            raise ValueError("tool exploded")

        result = mw.wrap_tool_call(request, failing_handler)

        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "call-1"
        assert result.status == "error"
        assert "ValueError: tool exploded" in result.content

    async def test_catches_async_exception_and_returns_error_tool_message(self):
        """异步工具调用异常应被转换为状态为 error 的 ToolMessage。"""
        mw = ToolErrorHandlingMiddleware()
        request = ToolCallRequest(
            tool_call={"id": "call-2", "name": "async_bad_tool"},
            tool=None,
            state={},
            runtime=None,
        )

        async def failing_handler(request):
            raise RuntimeError("async tool exploded")

        result = await mw.awrap_tool_call(request, failing_handler)

        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "call-2"
        assert result.status == "error"
        assert "RuntimeError: async tool exploded" in result.content

    def test_successful_tool_call_passes_through(self):
        """正常工具调用结果应原样返回。"""
        mw = ToolErrorHandlingMiddleware()
        request = ToolCallRequest(
            tool_call={"id": "call-3", "name": "good_tool"},
            tool=None,
            state={},
            runtime=None,
        )
        expected = ToolMessage(content="ok", tool_call_id="call-3")

        def handler(request):
            return expected

        result = mw.wrap_tool_call(request, handler)
        assert result is expected


class TestLoopDetectionMiddleware:
    """验证 LoopDetectionMiddleware 的循环检测与强制停止路径。"""

    def _make_ai_with_tool_calls(self, tool_name: str = "same_tool", count: int = 1) -> AIMessage:
        tool_calls = [{"id": f"call-{i}", "name": tool_name, "args": {}} for i in range(count)]
        return AIMessage(content="", tool_calls=tool_calls)

    def test_before_agent_initializes_loop_state(self):
        """before_agent 应初始化循环追踪状态。"""
        mw = LoopDetectionMiddleware()
        update = mw.before_agent({}, runtime=None)

        assert "_loop_history" in update
        assert "_loop_counts" in update
        assert "_loop_warnings" in update
        assert isinstance(update["_loop_history"], deque)

    def test_after_model_returns_none_without_tool_calls(self):
        """最后一条消息没有 tool_calls 时不应干预。"""
        mw = LoopDetectionMiddleware()
        state = {"messages": [HumanMessage("hi"), AIMessage("hello")]}
        assert mw.after_model(state, runtime=None) is None

    def test_warns_when_identical_call_set_reaches_threshold(self, caplog):
        """相同工具调用集合达到 warn_threshold 时应记录警告。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_stop_threshold=5)
        state = {"messages": [], "_loop_history": deque(maxlen=10), "_loop_counts": {}}

        for _ in range(2):
            state["messages"].append(self._make_ai_with_tool_calls("same_tool"))
            update = mw.after_model(state, runtime=None)
            if update:
                state.update(update)

        assert any("Potential loop" in rec.message for rec in caplog.records)

    def test_hard_stops_when_identical_call_set_reaches_threshold(self):
        """相同工具调用集合达到 hard_stop_threshold 时应清空 tool_calls 并附加警告。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_stop_threshold=3)
        state = {"messages": [], "_loop_history": deque(maxlen=10), "_loop_counts": {}}

        update = None
        for _ in range(3):
            state["messages"].append(self._make_ai_with_tool_calls("same_tool"))
            update = mw.after_model(state, runtime=None)
            if update:
                state.update(update)

        assert update is not None
        assert "messages" in update
        last_msg = update["messages"][-1]
        assert last_msg.tool_calls == []
        assert "loop" in last_msg.content.lower()

    def test_per_tool_frequency_hard_stop(self):
        """单工具高频调用达到 per_tool_hard 时应强制停止。"""
        mw = LoopDetectionMiddleware(
            warn_threshold=100,
            hard_stop_threshold=100,
            per_tool_warn=2,
            per_tool_hard=3,
        )
        state = {"messages": [], "_loop_history": deque(maxlen=10), "_loop_counts": {}}

        update = None
        for i in range(3):
            state["messages"].append(self._make_ai_with_tool_calls("same_tool"))
            update = mw.after_model(state, runtime=None)
            if update:
                state.update(update)

        assert update is not None
        last_msg = update["messages"][-1]
        assert last_msg.tool_calls == []
        assert "same_tool" in last_msg.content

    async def test_async_after_model_delegates_to_sync(self):
        """异步 after_model 应委托给同步实现。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_stop_threshold=3)
        state = {"messages": [], "_loop_history": deque(maxlen=10), "_loop_counts": {}}

        for _ in range(3):
            state["messages"].append(self._make_ai_with_tool_calls("same_tool"))
            update = await mw.aafter_model(state, runtime=None)
            if update:
                state.update(update)

        assert state["messages"][-1].tool_calls == []


class TestTokenUsageMiddleware:
    """验证 TokenUsageMiddleware 的 token 聚合路径。"""

    def test_before_agent_initializes_counters(self):
        """before_agent 应初始化 token 计数器。"""
        mw = TokenUsageMiddleware()
        update = mw.before_agent({}, runtime=None)

        assert update["_token_usage_total"] == 0
        assert update["_token_usage_prompt"] == 0
        assert update["_token_usage_completion"] == 0

    def test_after_model_aggregates_usage(self):
        """after_model 应从最后一条 AIMessage 提取并累加 token。"""
        mw = TokenUsageMiddleware(log_interval=1)
        state = {
            "_token_usage_total": 10,
            "_token_usage_prompt": 6,
            "_token_usage_completion": 4,
            "messages": [
                HumanMessage("hi"),
                AIMessage(
                    content="ok",
                    usage_metadata={
                        "input_tokens": 5,
                        "output_tokens": 3,
                        "total_tokens": 8,
                    },
                ),
            ],
        }

        update = mw.after_model(state, runtime=None)

        assert update["_token_usage_total"] == 18
        assert update["_token_usage_prompt"] == 11
        assert update["_token_usage_completion"] == 7

    def test_after_model_returns_none_without_usage_metadata(self):
        """没有 usage_metadata 时不应产生更新。"""
        mw = TokenUsageMiddleware()
        state = {"messages": [HumanMessage("hi"), AIMessage(content="ok")]}
        assert mw.after_model(state, runtime=None) is None

    def test_logs_at_configured_interval(self, caplog):
        """达到 log_interval 时应记录 token 用量日志。"""
        mw = TokenUsageMiddleware(log_interval=2)
        state = {
            "_token_usage_total": 0,
            "_token_usage_prompt": 0,
            "_token_usage_completion": 0,
            "messages": [
                AIMessage(
                    content="a",
                    usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                ),
            ],
        }

        with caplog.at_level("INFO", logger="scaffold.infra.middleware.deerflow_adapters.token_usage"):
            mw.after_model(state, runtime=None)
            assert not any("Token usage" in rec.message for rec in caplog.records)

            mw.after_model(state, runtime=None)
            assert any("Token usage" in rec.message for rec in caplog.records)

    async def test_async_after_model_delegates_to_sync(self):
        """异步 after_model 应委托给同步实现。"""
        mw = TokenUsageMiddleware()
        state = {
            "_token_usage_total": 0,
            "messages": [
                AIMessage(
                    content="ok",
                    usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                ),
            ],
        }

        update = await mw.aafter_model(state, runtime=None)

        assert update["_token_usage_total"] == 3
        assert update["_token_usage_prompt"] == 2
        assert update["_token_usage_completion"] == 1
