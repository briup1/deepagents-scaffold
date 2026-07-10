"""Integration tests for the FastAPI Gateway."""

from fastapi.testclient import TestClient


def test_ag_ui_endpoint_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert any(path.startswith("/agent") for path in paths), "ag-ui /agent endpoint not registered"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_agents(client):
    response = client.get("/api/agents/")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data


def test_list_tools(client):
    response = client.get("/api/tools/")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data


def test_runs_stream_removed(client: TestClient) -> None:
    response = client.post(
        "/api/runs/stream",
        json={"assistant_id": "default", "input": {"messages": []}},
    )
    assert response.status_code == 404


def test_create_thread(client):
    response = client.post("/api/threads/", json={})
    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data


def test_get_thread_after_create(client):
    response = client.post("/api/threads/", json={})
    assert response.status_code == 200
    data = response.json()
    thread_id = data["thread_id"]

    response = client.get(f"/api/threads/{thread_id}")
    assert response.status_code == 200
    assert response.json()["thread_id"] == thread_id

    response = client.get(f"/api/threads/{thread_id}/state")
    assert response.status_code == 200
    state_data = response.json()
    assert state_data["thread_id"] == thread_id
    assert "state" in state_data


def test_get_thread_not_found(client):
    response = client.get("/api/threads/nonexistent")
    assert response.status_code == 404


def test_code_review_tools_listed(client):
    response = client.get("/api/tools/")
    assert response.status_code == 200
    data = response.json()
    names = {t["name"] for t in data["tools"]}
    expected = {
        "read_file",
        "list_files",
        "run_ruff",
        "run_pytest",
        "explain_symbol",
        "generate_patch",
        "write_file",
    }
    assert expected.issubset(names)
