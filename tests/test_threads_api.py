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


def test_delete_thread(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    thread_id = res.json()["thread_id"]

    res = client.delete(f"/api/threads/{thread_id}")
    assert res.status_code == 200
    assert res.json() == {"thread_id": thread_id, "deleted": True}

    # 历史表与 checkpoint 均已清除
    res = client.get(f"/api/threads/{thread_id}")
    assert res.status_code == 404


def test_delete_thread_not_found(client: TestClient) -> None:
    res = client.delete("/api/threads/nonexistent")
    assert res.status_code == 404


def test_delete_agent_threads(client: TestClient) -> None:
    ids = []
    for _ in range(2):
        res = client.post("/api/threads/", json={"agent_id": "default"})
        ids.append(res.json()["thread_id"])

    res = client.delete("/api/agents/default/threads")
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "default"
    assert data["deleted_count"] >= 2
    for thread_id in ids:
        assert thread_id in data["deleted_thread_ids"]

    res = client.get("/api/threads/?agent_id=default")
    assert res.json()["threads"] == []
