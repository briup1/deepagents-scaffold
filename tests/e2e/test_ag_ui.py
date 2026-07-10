"""ag-ui /agent 端点集成测试。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _parse_ag_ui_events(response) -> list[dict]:
    """解析 ag-ui SSE 响应，每条 data 线为 JSON payload。"""
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


def _agent_payload(thread_id: str, run_id: str, message_id: str, content: str) -> dict:
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [{"id": message_id, "role": "user", "content": content}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def test_agent_stream_returns_run_lifecycle(client: TestClient) -> None:
    payload = _agent_payload("thread-test-001", "run-test-001", "msg-001", "hello")
    response = client.post("/agent", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200

    events = _parse_ag_ui_events(response)
    types = [e.get("type") for e in events]
    assert "RUN_STARTED" in types
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert "TEXT_MESSAGE_END" in types
    assert "RUN_FINISHED" in types


def test_agent_stream_continues_thread(client: TestClient) -> None:
    thread_id = "thread-test-002"
    r1 = client.post(
        "/agent",
        json=_agent_payload(thread_id, "run-test-002-a", "msg-001", "hello"),
        headers={"Accept": "text/event-stream"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/agent",
        json=_agent_payload(thread_id, "run-test-002-b", "msg-002", "what did i say"),
        headers={"Accept": "text/event-stream"},
    )
    assert r2.status_code == 200

    events = _parse_ag_ui_events(r2)
    types = [e.get("type") for e in events]
    assert "RUN_STARTED" in types
    assert "RUN_FINISHED" in types
