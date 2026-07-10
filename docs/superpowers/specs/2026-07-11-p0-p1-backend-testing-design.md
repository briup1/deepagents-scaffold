# P0/P1 后端测试设计文档

## 背景

当前项目后端已具备单元测试与基于 `fastapi.testclient.TestClient` 的集成测试（`tests/test_api.py` 等），但缺少两类关键测试：

1. **P0 集成测试**：覆盖 `/api/runs/stream`、`/api/runs/wait` 等核心对话链路，验证 FastAPI 路由、Agent 工厂、Worker、StreamBridge 的协作。
2. **P1 真实进程冒烟测试**：启动真实 `uvicorn` 服务进程，通过真实 HTTP 调用验证服务可启动、健康检查通过、能跑完一条完整对话。

本设计基于已有 `scaffold.infra.models.mock:MockChatModel`，通过测试专用配置替换真实 LLM，实现低成本、可重复、CI 友好的端到端测试。

## 目标

- 补齐 P0：使用 `TestClient` 覆盖 stream / wait / 线程状态查询链路。
- 补齐 P1：使用真实 uvicorn 进程覆盖服务生命周期与真实 HTTP 对话。
- 保证测试不调用真实 LLM API，不写生产数据，不污染开发环境。
- 所有新增测试统一纳入 `pytest tests/e2e/`，并可通过 `pytest` 全量回归。

## 非目标

- 不测试前端页面。
- 不测试真实 LLM 推理质量。
- 不测试外部工具（ruff、pytest 等）的真实执行结果。
- 不改动生产业务逻辑或生产配置文件。

## 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     pytest tests/e2e/                        │
├─────────────────────┬───────────────────────────────────────┤
│  P0 TestClient E2E  │  P1 真实进程 E2E                       │
│  tests/e2e/test_api_runs.py │ tests/e2e/test_service_lifecycle.py │
├─────────────────────┴───────────────────────────────────────┤
│              共用 fixtures (tests/conftest.py)               │
│         client, test_config_path, e2e_live_server            │
├─────────────────────────────────────────────────────────────┤
│              测试专用配置 (config.test.yaml)                  │
│       MockChatModel 作为默认模型 + 临时 SQLite 目录           │
└─────────────────────────────────────────────────────────────┘
```

## 关键设计决策

### 1. 假模型方案

使用项目已有的 `scaffold.infra.models.mock:MockChatModel`，在 `config.test.yaml` 中配置：

```yaml
models:
  - name: mock-default
    display_name: Mock Default
    use: scaffold.infra.models.mock:MockChatModel
    model: mock
    response_text: "这是一个来自 MockChatModel 的固定响应。"
```

优点：
- 无需新增假模型实现。
- 完全遵循项目"配置驱动"原则。
- 对生产代码零侵入。

### 2. 测试配置隔离

通过 `SCAFFOLD_CONFIG_PATH` 环境变量指定 `config.test.yaml`：

```python
@pytest.fixture
def test_config_path() -> Path:
    return Path(__file__).parent.parent / "config.test.yaml"

@pytest.fixture(autouse=True)
def _use_test_config(test_config_path, monkeypatch):
    monkeypatch.setenv("SCAFFOLD_CONFIG_PATH", str(test_config_path))
    reload_app_config()
    yield
    reload_app_config()
```

同时 `config.test.yaml` 中：
- SQLite 目录指向临时路径 `./tmp_tests/data`
- 记忆系统关闭或指向临时路径
- 不启用外部通道（飞书/Slack）

### 3. TestClient vs 真实进程

| 维度 | P0 TestClient | P1 真实进程 |
|------|--------------|------------|
| 测试文件 | `tests/e2e/test_api_runs.py` | `tests/e2e/test_service_lifecycle.py` |
| 服务启动 | 否 | 是（subprocess 启动 uvicorn） |
| 走真实 HTTP | 否 | 是 |
| 验证重点 | 业务逻辑正确 | 服务生命周期 + 网络栈正确 |

### 4. 随机端口

P1 测试使用随机端口启动 uvicorn（`--port 0`），避免端口冲突，支持未来并行化。

## 变更清单

### 新增文件

- `config.test.yaml`
- `tests/e2e/__init__.py`
- `tests/e2e/test_api_runs.py`
- `tests/e2e/test_service_lifecycle.py`

### 修改文件

- `tests/conftest.py`：扩展现有 fixture，支持测试配置加载。
- `src/scaffold/infra/models/mock.py`：可选扩展，支持自定义响应文本以覆盖更多场景。

### 不修改文件

- `config.yaml`（生产配置）
- `src/scaffold/api/app.py`
- 业务路由代码

## 测试用例设计

### P0：TestClient 集成测试

#### `test_stream_run_returns_end_event`
- 调用 `POST /api/runs/stream`，payload 包含 `assistant_id=default` 和一条用户消息。
- 使用 `TestClient` 读取 SSE 流。
- 断言：收到至少一个 `message` 事件，最终收到 `event: end`。

#### `test_wait_run_returns_checkpoint`
- 调用 `POST /api/runs/wait`，payload 同 stream。
- 断言：返回 JSON 包含 `run_id`、`thread_id`、`checkpoint`。

#### `test_thread_state_after_run`
- 调用 `POST /api/threads/` 创建线程。
- 调用 `POST /api/runs/wait` 在该线程上运行。
- 调用 `GET /api/threads/{thread_id}/state`。
- 断言：返回状态包含该线程 ID。

### P1：真实进程冒烟测试

#### `test_health_check_live_server`
- 使用 `subprocess` 启动 uvicorn，监听随机端口。
- 等待 `/health` 返回 200 且 `status == "healthy"`。
- 终止进程，断言退出码为 0。

#### `test_stream_run_live_server`
- 启动真实 uvicorn 服务。
- 使用 `httpx` 发送 `POST /api/runs/stream`。
- 读取 SSE 响应，断言最终收到 `event: end`。
- 终止进程，断言退出码为 0。

## 影响范围

### 代码影响
- 新增测试代码，不修改生产代码。
- 可能需要在 `pyproject.toml` 或依赖中添加 `httpx`（如尚未安装）。

### 运行时影响
- 无。`config.test.yaml` 仅在测试中使用。

### CI 影响
- `pytest tests/e2e/` 可作为新的 CI 步骤。
- 全量 `pytest` 包含新增测试。

## 行为边界

### 测试内必须验证
- Stream 模式返回完整 SSE 事件流。
- Wait 模式返回 checkpoint。
- 线程创建后可查询状态。
- 真实服务能启动、响应、关闭。

### 测试内不验证
- 真实 LLM 的推理质量。
- 外部工具的真实执行结果。
- 前端页面渲染。
- 认证/限流中间件的复杂行为。

### 测试前提
- 不需要真实 API key。
- 不依赖外部网络。
- 测试数据写入临时目录。

## 验收标准

### 功能验收
- [ ] `config.test.yaml` 存在且使用 `MockChatModel`。
- [ ] `tests/e2e/test_api_runs.py` 至少包含 3 个通过的 P0 用例。
- [ ] `tests/e2e/test_service_lifecycle.py` 至少包含 2 个通过的 P1 用例。
- [ ] `pytest tests/e2e/` 全部通过。

### 质量验收
- [ ] 新增代码通过 `ruff check src tests`。
- [ ] 新增代码通过 `ruff format src tests`。
- [ ] 全量 `pytest` 仍然通过。

### 环境验收
- [ ] 测试不调用真实 LLM API。
- [ ] 测试不污染 `./data` 目录。
- [ ] P1 测试结束后无残留 uvicorn 进程。

## 后续可扩展方向

- 工具调用链路 E2E：让 MockChatModel 返回 `tool_calls`，验证 Agent 调用工具并处理结果。
- 认证中间件 E2E：配置 `SCAFFOLD_API_KEY`，验证未认证请求被拒绝。
- 多轮对话 E2E：验证同一 thread 上多轮 run 的记忆和状态连续性。
