"""ag-ui /agent 端点集成测试。"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from ag_ui.core import (
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi.testclient import TestClient

from scaffold.api.ag_ui import _build_ag_ui_agent, _eager_event_generator
from scaffold.api.stream_listeners import AgUILogListener
from scaffold.infra.config.app_config import get_app_config


def _parse_ag_ui_events(response: httpx.Response) -> list[dict[str, Any]]:
    """解析 ag-ui SSE 响应，仅收集 data: 行作为 JSON payload。"""
    events = []
    payload = ""
    for raw in response.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line:
            if payload:
                events.append(json.loads(payload))
                payload = ""
            continue
        if line.startswith("data: "):
            payload = line[len("data: ") :]
    if payload:
        events.append(json.loads(payload))
    return events


def _parse_sse_lines(lines: list[str]) -> list[dict[str, Any]]:
    """从 SSE 文本行或完整 SSE 事件块解析 data: payload。"""
    events = []
    payload = ""
    for item in lines:
        for line in item.splitlines():
            if not line:
                if payload:
                    events.append(json.loads(payload))
                    payload = ""
                continue
            if line.startswith("data: "):
                payload = line[len("data: ") :]
    if payload:
        events.append(json.loads(payload))
    return events


def _agent_payload(thread_id: str, run_id: str, message_id: str, content: str) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [{"id": message_id, "role": "user", "content": content}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


class _FakeAgent:
    """用于流控单元测试的伪 Agent，可按指定延迟产生事件。"""

    name = "fake"

    def __init__(self, events_with_delays: list[tuple[float, Any]]) -> None:
        self.events_with_delays = events_with_delays

    async def run(self, _input: RunAgentInput) -> AsyncGenerator[Any, None]:
        for delay, event in self.events_with_delays:
            if delay:
                await asyncio.sleep(delay)
            yield event


class _FailingAgent:
    """模拟运行中途抛错的 Agent，用于验证 RUN_ERROR 会被推送到前端。"""

    name = "failing"

    async def run(self, _input: RunAgentInput) -> AsyncGenerator[Any, None]:
        yield RunStartedEvent(threadId="t", runId="r")
        raise RuntimeError("boom")


class _FakeRequest:
    """模拟 FastAPI Request，支持 is_disconnected()。"""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


def _make_run_input() -> RunAgentInput:
    return RunAgentInput(
        threadId="thread-test",
        runId="run-test",
        state={},
        messages=[{"id": "msg-001", "role": "user", "content": "hello"}],
        tools=[],
        context=[],
        forwardedProps={},
    )


def _make_text_event_sequence() -> list[tuple[float, Any]]:
    return [
        (0.0, RunStartedEvent(threadId="t", runId="r")),
        (0.0, TextMessageStartEvent(messageId="m1")),
        (0.0, TextMessageContentEvent(messageId="m1", delta="hi")),
        (0.0, TextMessageEndEvent(messageId="m1")),
        (0.0, RunFinishedEvent(threadId="t", runId="r")),
    ]


def test_agent_stream_returns_run_lifecycle(client: TestClient) -> None:
    payload = _agent_payload("thread-test-001", "run-test-001", "msg-001", "hello")
    response = client.post("/agent/default", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200

    events = _parse_ag_ui_events(response)
    types = [e.get("type") for e in events]
    assert "RUN_STARTED" in types
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert "TEXT_MESSAGE_END" in types
    assert "RUN_FINISHED" in types


def test_agent_stream_persists_user_message(client: TestClient) -> None:
    """调用 /agent 后，用户消息应被持久化到历史表并可查询。"""
    thread_id = f"thread-persist-{uuid.uuid4()}"
    message_id = f"msg-persist-{uuid.uuid4()}"
    payload = _agent_payload(thread_id, f"run-persist-{uuid.uuid4()}", message_id, "persist me")
    response = client.post("/agent/default", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200

    # 消费完整 SSE 流，确保后台 producer 完成
    for _ in response.iter_lines():
        pass

    res = client.get(f"/api/threads/{thread_id}/messages")
    assert res.status_code == 200
    data = res.json()
    assert data["thread_id"] == thread_id
    roles = [m["role"] for m in data["messages"]]
    assert "user" in roles


def test_agent_stream_continues_thread(client: TestClient) -> None:
    thread_id = "thread-test-002"
    r1 = client.post(
        "/agent/default",
        json=_agent_payload(thread_id, "run-test-002-a", "msg-001", "hello"),
        headers={"Accept": "text/event-stream"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/agent/default",
        json=_agent_payload(thread_id, "run-test-002-b", "msg-002", "what did i say"),
        headers={"Accept": "text/event-stream"},
    )
    assert r2.status_code == 200

    events = _parse_ag_ui_events(r2)
    types = [e.get("type") for e in events]
    assert "RUN_STARTED" in types
    assert "RUN_FINISHED" in types

    # 验证线程状态确实延续：助手回复中应提到之前说过的 "hello"
    assistant_text = ""
    current_message_id: str | None = None
    for event in events:
        event_type = event.get("type")
        if event_type == "TEXT_MESSAGE_START":
            current_message_id = event.get("messageId")
            assistant_text = ""
        elif event_type == "TEXT_MESSAGE_CONTENT" and current_message_id:
            assistant_text += event.get("delta", "")
        elif event_type == "TEXT_MESSAGE_END":
            current_message_id = None

    assert any(keyword in assistant_text.lower() for keyword in ("hello", "你刚才说", "said")), (
        f"assistant response did not reference prior message: {assistant_text!r}"
    )


@pytest.mark.asyncio
async def test_eager_streaming_completes_despite_slow_consumer() -> None:
    """消费端暂停时，后台 graph 仍继续执行，最终能收到 RUN_FINISHED。"""
    # 模拟一个产生事件较慢的 agent：RUN_STARTED 后立即产生，RUN_FINISHED 在 0.5s 后产生。
    events = [
        (0.0, RunStartedEvent(threadId="t", runId="r")),
        (0.5, TextMessageStartEvent(messageId="m1")),
        (0.5, TextMessageContentEvent(messageId="m1", delta="hi")),
        (0.5, TextMessageEndEvent(messageId="m1")),
        (0.5, RunFinishedEvent(threadId="t", runId="r")),
    ]
    agent = _FakeAgent(events)
    encoder = EventEncoder()
    request = _FakeRequest()

    gen = _eager_event_generator(
        agent,
        _make_run_input(),
        encoder,
        request,
        [AgUILogListener()],
        heartbeat_interval=1.0,
    )

    chunks: list[str] = []
    # 先读第一条（RUN_STARTED）
    chunks.append(await gen.__anext__())

    # 模拟消费端暂停 2 秒，期间后台 producer 应继续把事件写入队列
    await asyncio.sleep(2.0)

    # 继续读完剩余事件
    async for chunk in gen:
        chunks.append(chunk)

    data_events = _parse_sse_lines(chunks)
    types = [e.get("type") for e in data_events]
    assert "RUN_STARTED" in types
    assert "RUN_FINISHED" in types


@pytest.mark.asyncio
async def test_eager_streaming_emits_heartbeat_during_idle() -> None:
    """事件间隔超过心跳间隔时，应发送 SSE comment 维持连接。"""
    events = [
        (0.0, RunStartedEvent(threadId="t", runId="r")),
        (0.8, RunFinishedEvent(threadId="t", runId="r")),
    ]
    agent = _FakeAgent(events)
    encoder = EventEncoder()
    request = _FakeRequest()

    gen = _eager_event_generator(
        agent,
        _make_run_input(),
        encoder,
        request,
        [AgUILogListener()],
        heartbeat_interval=0.2,
    )

    chunks = [chunk async for chunk in gen]
    assert any(chunk == ":heartbeat\n\n" for chunk in chunks)

    data_events = _parse_sse_lines(chunks)
    types = [e.get("type") for e in data_events]
    assert "RUN_STARTED" in types
    assert "RUN_FINISHED" in types


@pytest.mark.asyncio
async def test_eager_streaming_emits_run_error_when_producer_fails() -> None:
    """后台 producer 抛错时，SSE 流应收到 RUN_ERROR，而不是静默结束。"""
    agent = _FailingAgent()
    encoder = EventEncoder()
    request = _FakeRequest()

    gen = _eager_event_generator(
        agent,
        _make_run_input(),
        encoder,
        request,
        [AgUILogListener()],
        heartbeat_interval=1.0,
    )

    chunks = [chunk async for chunk in gen]
    data_events = _parse_sse_lines(chunks)
    types = [e.get("type") for e in data_events]

    assert "RUN_STARTED" in types
    assert "RUN_ERROR" in types
    assert "RUN_FINISHED" not in types

    run_error = next(e for e in data_events if e.get("type") == "RUN_ERROR")
    assert "boom" in run_error.get("message", "")
    assert run_error.get("code") == "RuntimeError"


@pytest.mark.asyncio
async def test_eager_streaming_stops_on_disconnect() -> None:
    """客户端断连后，生成器应及时退出，避免后台任务空转。"""
    events = [
        (0.0, RunStartedEvent(threadId="t", runId="r")),
        (5.0, RunFinishedEvent(threadId="t", runId="r")),
    ]
    agent = _FakeAgent(events)
    encoder = EventEncoder()
    request = _FakeRequest(disconnected=True)

    gen = _eager_event_generator(
        agent,
        _make_run_input(),
        encoder,
        request,
        [AgUILogListener()],
        heartbeat_interval=0.1,
    )

    chunks = [chunk async for chunk in gen]
    # 第一条 RUN_STARTED 后立即检测到断开，不再发送后续事件或长时间等待
    assert all("RUN_FINISHED" not in chunk for chunk in chunks)


def test_build_ag_ui_agent_uses_configured_recursion_limit(
    _reset_app_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_build_ag_ui_agent 应把 app_config.agent.max_iterations 传入 LangGraphAgent 的 config。"""
    captured: dict[str, Any] = {}

    class _MockGraph:
        pass

    def _mock_get_agent(name: str) -> Any:
        return _MockGraph()

    def _mock_init(
        self,
        *,
        name: str,
        graph: Any,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        captured["name"] = name
        captured["graph"] = graph
        captured["config"] = config
        self.name = name
        self.description = description
        self.graph = graph
        self.config = config or {}

    monkeypatch.setattr("scaffold.api.ag_ui.get_agent", _mock_get_agent)
    monkeypatch.setattr(LangGraphAgent, "__init__", _mock_init)

    agent = _build_ag_ui_agent("default")

    expected_limit = get_app_config().agent.max_iterations
    assert agent.config.get("recursion_limit") == expected_limit, (
        f"expected recursion_limit={expected_limit}, got {agent.config!r}"
    )
    assert captured["name"] == "default"
    assert isinstance(captured["graph"], _MockGraph)
