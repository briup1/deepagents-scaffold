"""P0: FastAPI TestClient 集成测试 — 覆盖对话运行链路。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


def _sse_lines(response) -> list[dict[str, str]]:
    """将 SSE 响应解析为 {event, data} 列表。"""
    events = []
    current: dict[str, str] = {}
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = line[len("data: ") :]
        elif line.startswith("id: "):
            current["id"] = line[len("id: ") :]
    if current:
        events.append(current)
    return events


def test_stream_run_returns_end_event(client: TestClient) -> None:
    payload = {
        "assistant_id": "default",
        "input": {
            "messages": [{"role": "user", "content": "hello"}]
        },
        "stream_mode": "values",
    }
    response = client.post("/api/runs/stream", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200

    events = _sse_lines(response)
    event_names = [e.get("event") for e in events]
    assert "message" in event_names or "values" in event_names
    assert "end" in event_names

    end_event = next(e for e in events if e.get("event") == "end")
    data = json.loads(end_event["data"])
    assert "run_id" in data


def test_wait_run_returns_checkpoint(client: TestClient) -> None:
    payload = {
        "assistant_id": "default",
        "input": {
            "messages": [{"role": "user", "content": "hello"}]
        },
        "stream_mode": "values",
    }
    response = client.post("/api/runs/wait", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "run_id" in data
    assert "thread_id" in data
    assert "checkpoint" in data


def test_thread_state_after_run(client: TestClient) -> None:
    create_resp = client.post("/api/threads/", json={})
    assert create_resp.status_code == 200
    thread_id = create_resp.json()["thread_id"]

    run_payload = {
        "assistant_id": "default",
        "input": {
            "messages": [{"role": "user", "content": "hello"}]
        },
        "config": {
            "configurable": {"thread_id": thread_id}
        },
        "stream_mode": "values",
    }
    run_resp = client.post("/api/runs/wait", json=run_payload)
    assert run_resp.status_code == 200
    assert run_resp.json()["thread_id"] == thread_id

    state_resp = client.get(f"/api/threads/{thread_id}/state")
    assert state_resp.status_code == 200
    state_data = state_resp.json()
    assert state_data["thread_id"] == thread_id
    assert "state" in state_data
