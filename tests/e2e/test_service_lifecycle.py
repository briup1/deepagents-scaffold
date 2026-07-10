"""P1: 真实 uvicorn 进程 E2E 冒烟测试。"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


def _find_free_port() -> int:
    """获取一个可用的随机端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    """轮询等待服务可用。"""
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.2)
    raise TimeoutError(f"Server did not become ready at {url}: {last_error}")


def _parse_sse(response: httpx.Response) -> list[dict[str, str]]:
    """解析 httpx SSE 响应。"""
    events = []
    current: dict[str, str] = {}
    for line in response.iter_lines():
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


@pytest.fixture
def live_server(test_config_path: Path):
    """启动真实 uvicorn 服务，返回 base_url 与进程对象。"""
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **dict(subprocess.os.environ),
        "SCAFFOLD_CONFIG_PATH": str(test_config_path),
        "PYTHONPATH": "src",
    }

    proc = subprocess.Popen(
        [
            "uv", "run", "uvicorn",
            "scaffold.api.app:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_server(f"{base_url}/health")
        yield {"base_url": base_url, "process": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_health_check_live_server(live_server: dict) -> None:
    base_url = live_server["base_url"]
    response = httpx.get(f"{base_url}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_stream_run_live_server(live_server: dict) -> None:
    base_url = live_server["base_url"]
    payload = {
        "assistant_id": "default",
        "input": {
            "messages": [{"role": "user", "content": "hello"}]
        },
        "stream_mode": "values",
    }
    response = httpx.post(
        f"{base_url}/api/runs/stream",
        json=payload,
        headers={"Accept": "text/event-stream"},
        timeout=30.0,
    )
    assert response.status_code == 200

    events = _parse_sse(response)
    event_names = [e.get("event") for e in events]
    assert "end" in event_names

    end_event = next(e for e in events if e.get("event") == "end")
    data = json.loads(end_event["data"])
    assert "run_id" in data
