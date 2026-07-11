# P0/P1 后端测试实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 P0 TestClient 集成测试与 P1 真实进程 E2E 冒烟测试，使用 MockChatModel 替换真实 LLM，统一纳入 pytest 与 CI。

**Architecture:** 新增 `config.test.yaml` 作为测试唯一配置来源；扩展 `tests/conftest.py` 提供测试配置加载、TestClient、真实服务进程三类 fixture；新增 `tests/e2e/test_api_runs.py` 覆盖 stream/wait/线程状态；新增 `tests/e2e/test_service_lifecycle.py` 覆盖真实 uvicorn 进程生命周期。

**Tech Stack:** pytest, fastapi.testclient.TestClient, httpx, uvicorn, subprocess, MockChatModel

## Global Constraints

- 所有新增代码必须位于 `tests/` 或 `config.test.yaml`，不修改生产业务代码。
- 测试配置必须通过 `SCAFFOLD_CONFIG_PATH` 或 `get_app_config(config_path=...)` 指定 `config.test.yaml`。
- `config.test.yaml` 必须使用 `scaffold.infra.models.mock:MockChatModel` 作为默认模型。
- SQLite 与记忆数据必须写入临时目录，避免污染 `./data`。
- 新增代码必须通过 `ruff check src tests` 与 `ruff format src tests`。
- 每个任务结束后必须能独立运行相关测试。

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `config.test.yaml` | 新建 | 测试专用配置，MockChatModel + 临时数据目录 |
| `tests/e2e/__init__.py` | 新建 | 标记 `tests/e2e/` 为包 |
| `tests/conftest.py` | 修改 | 扩展 fixture：`test_config_path`、`_reset_app_config`、`client`、`live_server` |
| `tests/e2e/test_api_runs.py` | 新建 | P0 TestClient 集成测试 |
| `tests/e2e/test_service_lifecycle.py` | 新建 | P1 真实进程 E2E 测试 |
| `src/scaffold/infra/models/mock.py` | 可选修改 | 扩展 MockChatModel 支持自定义响应文本参数 |

---

### Task 1: 创建测试专用配置

**Files:**
- Create: `config.test.yaml`

**Interfaces:**
- Consumes: 无
- Produces: 一个可被 `SCAFFOLD_CONFIG_PATH` 指向的完整测试配置

- [ ] **Step 1: 编写 config.test.yaml**

在项目根目录创建 `config.test.yaml`，内容如下（基于生产 `config.yaml` 删减并替换模型）：

```yaml
config_version: 1
log_level: info

models:
  - name: mock-default
    display_name: Mock Default
    use: scaffold.infra.models.mock:MockChatModel
    model: mock
    response_text: "这是一个来自 MockChatModel 的固定响应。"

agent:
  max_iterations: 500
  drop_error_from_history: true

tools:
  - name: read_file
    use: scaffold.plugins.tools.code_review:read_file
  - name: list_files
    use: scaffold.plugins.tools.code_review:list_files
  - name: run_ruff
    use: scaffold.plugins.tools.code_review:run_ruff
  - name: run_pytest
    use: scaffold.plugins.tools.code_review:run_pytest
  - name: explain_symbol
    use: scaffold.plugins.tools.code_review:explain_symbol
  - name: generate_patch
    use: scaffold.plugins.tools.code_review:generate_patch
  - name: write_file
    use: scaffold.plugins.tools.code_review:write_file

tool_groups: []

skills:
  path: src/scaffold/plugins/skills
  container_path: /mnt/skills

middleware:
  items:
    - name: ToolErrorHandlingMiddleware
      enabled: true
    - name: DynamicContextMiddleware
      enabled: true
      kwargs:
        inject_date: true
        inject_memory: false
        memory_sources: []
    - name: LoopDetectionMiddleware
      enabled: true
      kwargs:
        warn_threshold: 3
        hard_stop_threshold: 5

profiles:
  harness:
    - name: default
      base_system_prompt: ""
      system_prompt_suffix: ""
      excluded_middleware: []
      excluded_tools: []
  default_harness: default

backend:
  type: filesystem
  filesystem:
    root_dir: /
  sandbox:
    provider: local
    timeout_seconds: 60
    mounts: []

memory:
  enabled: false
  injection_enabled: false
  storage_path: ./tmp_tests/memory.json
  debounce_seconds: 30
  model_name: null
  max_facts: 100
  fact_confidence_threshold: 0.7
  max_injection_tokens: 2000

subagents:
  enabled: false
  max_concurrent: 3
  timeout_seconds: 900

subagent_definitions:
  items: []

channels:
  langgraph_url: http://localhost:8000/api
  gateway_url: http://localhost:8000
  feishu:
    enabled: false
  slack:
    enabled: false

tracing:
  enabled: false
  providers: []

gateway:
  host: 127.0.0.1
  port: 8000
  enable_docs: false

database:
  backend: sqlite
  sqlite_dir: ./tmp_tests/data

stream_bridge:
  type: memory
  queue_maxsize: 256
```

- [ ] **Step 2: 验证配置可加载**

Run:
```bash
SCAFFOLD_CONFIG_PATH=config.test.yaml python -c "from scaffold.infra.config.app_config import get_app_config; c=get_app_config(); print(c.models[0].name)"
```

Expected output: `mock-default`

- [ ] **Step 3: 提交**

```bash
git add config.test.yaml
git commit -m "test: add test config with MockChatModel"
```

---

### Task 2: 扩展 conftest.py 支持测试配置

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `AppConfig.resolve_config_path`, `reload_app_config`
- Produces: fixtures `test_config_path`, `_reset_app_config`, `client`（已存在，扩展）

- [ ] **Step 1: 读取现有 conftest.py**

Read `tests/conftest.py`。

- [ ] **Step 2: 添加 fixture**

将 `tests/conftest.py` 修改为：

```python
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scaffold.api.app import create_app
from scaffold.infra.config.app_config import reload_app_config


@pytest.fixture(scope="session")
def project_root() -> Path:
    """返回项目根目录。"""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_config_path(project_root: Path) -> Path:
    """返回测试专用配置文件路径。"""
    return project_root / "config.test.yaml"


@pytest.fixture(autouse=True)
def _reset_app_config(test_config_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每次测试前重置配置缓存并强制使用 config.test.yaml。"""
    monkeypatch.setenv("SCAFFOLD_CONFIG_PATH", str(test_config_path))
    reload_app_config()
    yield
    reload_app_config()


@pytest.fixture
def client(_reset_app_config) -> TestClient:
    """创建使用测试配置的 TestClient。"""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 3: 运行现有测试验证无回归**

Run:
```bash
pytest tests/test_api.py -v
```

Expected: 全部通过。

- [ ] **Step 4: 提交**

```bash
git add tests/conftest.py
git commit -m "test: use config.test.yaml in TestClient fixture"
```

---

### Task 3: 实现 P0 TestClient 集成测试

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_api_runs.py`

**Interfaces:**
- Consumes: `client` fixture
- Produces: `tests/e2e/test_api_runs.py` 中的 3 个测试函数

- [ ] **Step 1: 创建包标记文件**

```bash
touch tests/e2e/__init__.py
```

- [ ] **Step 2: 编写 P0 测试**

创建 `tests/e2e/test_api_runs.py`：

```python
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
```

- [ ] **Step 3: 运行 P0 测试并观察失败**

Run:
```bash
pytest tests/e2e/test_api_runs.py -v
```

Expected: 可能失败（如 `thread state` 路由不存在或响应格式不同），根据实际失败调整断言。

- [ ] **Step 4: 调整断言直到通过**

如果失败，读取相关路由源码（`src/scaffold/api/routers/state.py`），根据实际响应调整断言。不要修改生产代码。

- [ ] **Step 5: 提交**

```bash
git add tests/e2e/__init__.py tests/e2e/test_api_runs.py
git commit -m "test(e2e): add P0 TestClient integration tests for runs"
```

---

### Task 4: 实现 P1 真实进程 E2E 测试

**Files:**
- Create: `tests/e2e/test_service_lifecycle.py`

**Interfaces:**
- Consumes: `test_config_path` fixture, `httpx`
- Produces: `tests/e2e/test_service_lifecycle.py` 中的 2 个测试函数

- [ ] **Step 1: 确认 httpx 已安装**

Run:
```bash
python -c "import httpx; print(httpx.__version__)"
```

如果失败，安装：
```bash
uv pip install httpx
```

- [ ] **Step 2: 编写服务启动辅助函数**

创建 `tests/e2e/test_service_lifecycle.py`：

```python
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
```

- [ ] **Step 3: 运行 P1 测试**

Run:
```bash
pytest tests/e2e/test_service_lifecycle.py -v
```

Expected: 通过。如果端口探测失败，增加等待时间或检查 uvicorn 启动日志。

- [ ] **Step 4: 提交**

```bash
git add tests/e2e/test_service_lifecycle.py
git commit -m "test(e2e): add P1 live server smoke tests"
```

---

### Task 5: 代码检查、全量测试与清理

**Files:**
- 无新增/修改文件

**Interfaces:**
- Consumes: 前面所有任务产生的文件
- Produces: 通过 ruff 与 pytest 的验证结果

- [ ] **Step 1: 运行代码检查**

Run:
```bash
ruff check src tests
ruff format src tests
```

Expected: 无错误。

- [ ] **Step 2: 运行全量测试**

Run:
```bash
pytest -v
```

Expected: 全部通过。

- [ ] **Step 3: 清理临时测试数据**

Run:
```bash
rm -rf tmp_tests
```

- [ ] **Step 4: 最终提交**

```bash
git add .
git commit -m "test(e2e): complete P0/P1 backend end-to-end tests"
```

---

## Spec Coverage Check

| 设计文档要求 | 覆盖任务 |
|-------------|---------|
| `config.test.yaml` 使用 MockChatModel | Task 1 |
| P0 stream/wait/线程状态测试 | Task 3 |
| P1 真实进程启动/健康/流式测试 | Task 4 |
| 测试配置隔离 | Task 2 |
| 不修改生产代码 | 全局约束 |
| ruff + pytest 通过 | Task 5 |

## Placeholder Scan

- 无 TBD/TODO
- 无 "implement later"
- 所有步骤包含具体代码或命令
- 所有文件路径绝对

## Type Consistency

- `test_config_path: Path`
- `client: TestClient`
- `live_server: dict` 包含 `base_url: str` 与 `process: subprocess.Popen`

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-07-11-p0-p1-backend-testing-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
