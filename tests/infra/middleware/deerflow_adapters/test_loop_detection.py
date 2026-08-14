"""Tests for LoopDetectionMiddleware."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from scaffold.infra.middleware.deerflow_adapters.loop_detection import (
    LoopDetectionMiddleware,
)


class TestLoopDetectionMiddleware:
    def _make_state(self, tool_calls, history=None, counts=None):
        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="", tool_calls=tool_calls),
        ]
        state: dict = {"messages": messages}
        if history is not None:
            state["_loop_history"] = history
        if counts is not None:
            state["_loop_counts"] = counts
        return state

    def test_hard_stop_clears_pending_tool_calls(self):
        """达到 hard_stop 阈值时，应清空最后 AI 消息的 tool_calls，避免在 assistant 与待执行的 tool 响应之间插入 SystemMessage。"""
        mw = LoopDetectionMiddleware(hard_stop_threshold=3, warn_threshold=2)
        tool_calls = [
            {
                "id": "call-1",
                "name": "read_file",
                "args": {"path": "x"},
                "type": "tool_call",
            }
        ]

        state = self._make_state(tool_calls)
        # 前两次调用仅更新历史
        for _ in range(2):
            update = mw.after_model(state, None)
            assert update is not None
            assert "messages" not in update
            state.update(update)

        # 第三次触发 hard stop
        result = mw.after_model(state, None)
        assert result is not None
        assert "messages" in result

        updated_messages = result["messages"]
        last_msg = updated_messages[-1]
        assert isinstance(last_msg, AIMessage)
        assert last_msg.tool_calls == []
        assert "loop" in (last_msg.content or "").lower()

        # 不应在仍带 tool_calls 的 assistant 消息后插入 SystemMessage
        assert not any(isinstance(m, SystemMessage) for m in updated_messages)

    def test_per_tool_hard_stop_clears_pending_tool_calls(self):
        """单个工具高频达到 hard stop 时，同样应清空 tool_calls。"""
        mw = LoopDetectionMiddleware(per_tool_hard=3, per_tool_warn=2)
        tool_calls = [
            {
                "id": "call-1",
                "name": "read_file",
                "args": {"path": "x"},
                "type": "tool_call",
            }
        ]

        state = self._make_state(tool_calls)
        for _ in range(2):
            update = mw.after_model(state, None)
            assert update is not None
            assert "messages" not in update
            state.update(update)

        result = mw.after_model(state, None)
        assert result is not None
        assert "messages" in result

        updated_messages = result["messages"]
        last_msg = updated_messages[-1]
        assert isinstance(last_msg, AIMessage)
        assert last_msg.tool_calls == []

    def test_warn_threshold_does_not_modify_messages(self):
        """仅达到 warn 阈值时不应修改消息列表。"""
        mw = LoopDetectionMiddleware(warn_threshold=2, hard_stop_threshold=5)
        tool_calls = [
            {
                "id": "call-1",
                "name": "read_file",
                "args": {"path": "x"},
                "type": "tool_call",
            }
        ]

        state = self._make_state(tool_calls)
        for _ in range(2):
            update = mw.after_model(state, None)
            assert update is not None
            assert "messages" not in update
            state.update(update)

        # 仍处于 warn 阶段，消息不应被改动
        assert state["messages"][-1].tool_calls == tool_calls

    def test_no_tool_calls_does_nothing(self):
        """最后一条消息没有 tool_calls 时不应干预。"""
        mw = LoopDetectionMiddleware()
        state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi")]}
        result = mw.after_model(state, None)
        assert result is None
