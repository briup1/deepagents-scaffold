"""Integration tests for the FastAPI Gateway."""

import pytest


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


def test_create_thread(client):
    response = client.post("/api/threads/", json={})
    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data


def test_get_thread_not_found(client):
    response = client.get("/api/threads/nonexistent")
    assert response.status_code == 404
