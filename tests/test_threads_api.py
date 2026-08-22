"""Threads API 测试。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_create_and_list_threads(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    assert res.status_code == 200
    thread_id = res.json()["thread_id"]

    res = client.get("/api/threads/?agent_id=default")
    assert res.status_code == 200
    data = res.json()
    assert any(t["thread_id"] == thread_id for t in data["threads"])


def test_get_thread_messages_empty(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    thread_id = res.json()["thread_id"]

    res = client.get(f"/api/threads/{thread_id}/messages")
    assert res.status_code == 200
    assert res.json()["messages"] == []


def test_get_thread_messages_returns_messages(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    thread_id = res.json()["thread_id"]

    # 通过 /agent 端点产生一条用户消息并持久化到历史表
    payload = {
        "threadId": thread_id,
        "runId": "run-test-messages",
        "messages": [{"id": f"msg-test-{uuid.uuid4()}", "role": "user", "content": "hello"}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    response = client.post("/agent", json=payload, headers={"Accept": "text/event-stream"})
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
