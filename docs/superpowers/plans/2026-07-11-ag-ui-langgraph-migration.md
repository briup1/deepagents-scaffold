# ag-ui / LangGraph 原生集成迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 使用 ag-ui 开放协议彻底替代现有前后端通信，后端通过 `ag-ui-langgraph` 直接暴露 LangGraph graph，前端通过 `@ag-ui/client` 消费事件流。

**Architecture:** 后端在 lifespan 内 `create_agent` 之后将 DeepAgents 编译后的 graph 包装为 `LangGraphAgent`，并通过 `add_langgraph_fastapi_endpoint` 注册 `/agent` SSE 端点；前端使用 `HttpAgent` 建立会话并基于 ag-ui 事件回调驱动 React 组件状态。Vanilla JS 实现与旧的 `StreamBridge` / `runs.py` 自定义 SSE 流程被彻底移除。

**Tech Stack:** Python 3.12, FastAPI, ag-ui-langgraph, DeepAgents, LangGraph, React 18, TypeScript 5.6, Vite 5.4, Tailwind CSS 3.4, @ag-ui/client.

## Global Constraints

- 后端协议：ag-ui（基于 SSE 的事件协议）。
- 后端集成方式：`ag-ui-langgraph` 的 `add_langgraph_fastapi_endpoint(app, agent, "/agent")`，其中 `agent` 为 `LangGraphAgent(name=..., graph=graph)`。
- 前端 SDK：`@ag-ui/client` 的 `HttpAgent`。
- `/agent` 端点必须在 `create_agent("default", checkpointer=...)` 完成后注册，注册逻辑需放在 lifespan 内。
- 替换范围：后端移除 `/api/runs/stream` 自定义 SSE 端点及 `StreamBridge`、`run_worker` 相关发布逻辑；前端保留并迁移 React 版本，彻底移除 Vanilla JS 版本。
- 保留内容：健康检查、Agent/Tool 元数据端点、配置系统、模型工厂、工具注册、中间件链。
- Python 代码风格：ruff（line-length=120, target-version=py312）。
- 新增 Python 依赖必须通过 `uv add <package>` 安装。
- 所有 Python 函数必须带类型注解。
- 所有 AI 生成的文档使用中文。

---

## File Structure

### 新增

- `src/scaffold/api/ag_ui.py`：把 `core/agents.py` 编译好的 graph 注册为 ag-ui 端点。
- `tests/e2e/test_ag_ui.py`：`/agent` SSE 端点的集成测试。

### 修改

- `src/scaffold/api/app.py`：lifespan 内注册 ag-ui 端点；移除 `runs` router；移除 static 挂载。
- `src/scaffold/api/deps.py`：移除 `stream_bridge` 生命周期与依赖访问器。
- `src/web/src/api.ts`：改为 `HttpAgent`。
- `src/web/src/App.tsx`：改为 ag-ui 事件驱动。
- `src/web/src/components/Chat.tsx`：支持 reasoning、工具调用卡片。
- `src/web/index.html`：恢复为 Vite/React 入口。
- `src/scaffold/infra/config/app_config.py`：移除 `StreamBridgeConfig`。
- `config.yaml` / `config.test.yaml`：移除 `stream_bridge` 配置段。
- `src/scaffold/CLAUDE.md` / `src/web/CLAUDE.md`：移除 StreamBridge / Vanilla JS 描述。

### 删除

- `src/scaffold/api/routers/runs.py`
- `src/scaffold/runtime/stream_bridge/` 目录
- `src/scaffold/runtime/worker.py`
- `src/web/static/` 目录（含 `app.js`、`style.css`）
- `src/scaffold/api/ag_ui_poc.py`
- `src/web/poc.html`
- `src/web/src/poc.tsx`
- `tests/test_stream_bridge.py`
- `tests/e2e/test_api_runs.py`

---

### Task 1: 后端 — 注册 ag-ui `/agent` 端点

**Files:**
- Create: `src/scaffold/api/ag_ui.py`
- Modify: `src/scaffold/api/app.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `get_agent(name: str) -> CompiledStateGraph`、`list_agents() -> list[dict[str, Any]]`（来自 `scaffold.core.agents`）
- Produces: `register_ag_ui_endpoints(app: Any) -> None`，在 lifespan 内 `create_agent` 之后调用

- [x] **Step 1: 写验证端点注册的测试**

```python
def test_ag_ui_endpoint_registered(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert any(path.startswith("/agent") for path in paths), "ag-ui /agent endpoint not registered"
```

- [x] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_api.py::test_ag_ui_endpoint_registered -v
```

Expected: FAIL（`ag_ui.py` 不存在或函数未定义）

- [x] **Step 3: 实现 ag-ui 注册模块并接入 app.py**

创建 `src/scaffold/api/ag_ui.py`：

```python
"""ag-ui 集成：将已注册的 DeepAgents graph 托管为 /agent SSE 端点。"""

from __future__ import annotations

import logging
from typing import Any

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

from scaffold.core.agents import get_agent, list_agents

logger = logging.getLogger(__name__)


def _build_ag_ui_agent(name: str) -> LangGraphAgent:
    """包装已编译的 DeepAgents graph 为 ag-ui LangGraphAgent。"""
    graph = get_agent(name)
    return LangGraphAgent(name=name, graph=graph)


def register_ag_ui_endpoints(app: Any) -> None:
    """为每个已注册 agent 在 FastAPI app 上注册 ag-ui 端点。"""
    agents = list_agents()
    if not agents:
        logger.warning("No agents registered; skipping ag-ui endpoint registration")
        return

    for info in agents:
        name = info["name"]
        path = f"/agent/{name}" if len(agents) > 1 else "/agent"
        agent = _build_ag_ui_agent(name)
        add_langgraph_fastapi_endpoint(app, agent, path)
        logger.info("AG-UI endpoint registered: %s -> agent=%s", path, name)
```

修改 `src/scaffold/api/app.py`：

1. 将 `from scaffold.api.ag_ui_poc import register_ag_ui_endpoint` 替换为：

```python
from scaffold.api.ag_ui import register_ag_ui_endpoints
```

2. 将 router 导入中的 `runs` 移除：

```python
from scaffold.api.routers import agents, health, state, threads, tools
```

3. 在 lifespan 内把 `register_ag_ui_endpoint(app)` 替换为：

```python
register_ag_ui_endpoints(app)
```

4. 移除 `app.include_router(runs.router)`。

- [x] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_api.py::test_ag_ui_endpoint_registered tests/test_api.py::test_health_check tests/test_api.py::test_list_agents -v
```

Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/scaffold/api/ag_ui.py src/scaffold/api/app.py tests/test_api.py
git commit -m "feat(api): register ag-ui /agent endpoint and remove runs router wiring"
```

---

### Task 2: 后端 — 移除自定义 `/api/runs` router 与 stream_bridge 依赖

**Files:**
- Delete: `src/scaffold/api/routers/runs.py`
- Modify: `src/scaffold/api/deps.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `app.state.checkpointer` 仍由 `scaffold_runtime` 提供
- Produces: `scaffold_runtime(app)` 不再初始化 `stream_bridge`；`get_checkpointer(request)` 保持不变

- [x] **Step 1: 写验证旧端点已下线的测试**

```python
def test_runs_stream_removed(client):
    response = client.post(
        "/api/runs/stream",
        json={"assistant_id": "default", "input": {"messages": []}},
    )
    assert response.status_code == 404
```

- [x] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_api.py::test_runs_stream_removed -v
```

Expected: FAIL（返回 200，因为 `/api/runs/stream` 仍存在）

- [x] **Step 3: 删除 runs.py 并清理 deps.py**

```bash
git rm src/scaffold/api/routers/runs.py
```

修改 `src/scaffold/api/deps.py`：

1. 删除 `from scaffold.runtime.stream_bridge.async_provider import make_stream_bridge`
2. 在 `scaffold_runtime` 中删除以下代码：

```python
bridge = await stack.enter_async_context(make_stream_bridge(config.stream_bridge.model_dump()))
app.state.stream_bridge = bridge
logger.info("Stream bridge initialized (type=%s)", config.stream_bridge.type)
```

3. 删除整个 `get_stream_bridge(request: Request)` 函数。

修改后 `scaffold_runtime` 仅保留 checkpointer 初始化逻辑。

- [x] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_api.py::test_runs_stream_removed tests/test_api.py::test_health_check tests/test_api.py::test_list_agents tests/test_api.py::test_list_tools -v
```

Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/scaffold/api/deps.py tests/test_api.py
git commit -m "refactor(api): remove custom /api/runs router and stream_bridge dependency"
```

---

### Task 3: 后端 — 更新测试覆盖 ag-ui `/agent`

**Files:**
- Delete: `tests/test_stream_bridge.py`
- Delete: `tests/e2e/test_api_runs.py`
- Modify: `tests/e2e/test_service_lifecycle.py`
- Create: `tests/e2e/test_ag_ui.py`

**Interfaces:**
- Consumes: `POST /agent` SSE 端点，请求体含 `threadId`、`runId`、`messages`（每条消息必须有 `id`）
- Produces: 测试断言 `RUN_STARTED`、`TEXT_MESSAGE_*`、`RUN_FINISHED` 事件序列

- [x] **Step 1: 写新的 `/agent` 集成测试**

创建 `tests/e2e/test_ag_ui.py`：

```python
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
```

- [x] **Step 2: 运行新测试确认通过**

```bash
pytest tests/e2e/test_ag_ui.py -v
```

Expected: PASS（Task 1 已完成端点注册）

- [x] **Step 3: 删除旧测试并更新 E2E 生命周期测试**

```bash
git rm tests/test_stream_bridge.py tests/e2e/test_api_runs.py
```

修改 `tests/e2e/test_service_lifecycle.py`：

1. 删除 `test_stream_run_live_server`。
2. 新增 `test_agent_stream_live_server`：

```python
def test_agent_stream_live_server(live_server: dict) -> None:
    base_url = live_server["base_url"]
    payload = {
        "threadId": "thread-live-001",
        "runId": "run-live-001",
        "messages": [{"id": "msg-001", "role": "user", "content": "hello"}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    response = httpx.post(
        f"{base_url}/agent",
        json=payload,
        headers={"Accept": "text/event-stream"},
        timeout=30.0,
    )
    assert response.status_code == 200

    events = _parse_sse(response)
    event_names = [
        json.loads(e.get("data", "{}")).get("type")
        for e in events
        if e.get("data")
    ]
    assert "RUN_STARTED" in event_names
    assert "RUN_FINISHED" in event_names
```

- [x] **Step 4: 运行相关测试确认通过**

```bash
pytest tests/e2e/test_ag_ui.py tests/e2e/test_service_lifecycle.py::test_health_check_live_server tests/e2e/test_service_lifecycle.py::test_agent_stream_live_server -v
```

Expected: PASS（`test_agent_stream_live_server` 会启动真实 uvicorn 进程，耗时较长）

- [x] **Step 5: 提交**

```bash
git add tests/e2e/test_ag_ui.py tests/e2e/test_service_lifecycle.py
git commit -m "test(api): replace /api/runs tests with ag-ui /agent tests"
```

---

### Task 4: 后端 — 移除 StreamBridge 运行时与配置

**Files:**
- Delete: `src/scaffold/runtime/stream_bridge/` 目录下所有文件
- Delete: `src/scaffold/runtime/worker.py`
- Modify: `src/scaffold/infra/config/app_config.py`
- Modify: `config.yaml`
- Modify: `config.test.yaml`
- Test: `pytest`

**Interfaces:**
- Consumes: 已无其他模块引用 `StreamBridge` / `run_worker`
- Produces: 配置系统不再包含 `stream_bridge` 字段

- [x] **Step 1: 删除运行时文件**

```bash
git rm -r src/scaffold/runtime/stream_bridge
```

- [x] **Step 2: 删除 worker.py**

```bash
git rm src/scaffold/runtime/worker.py
```

- [x] **Step 3: 清理配置模型与配置文件**

修改 `src/scaffold/infra/config/app_config.py`：

1. 删除 `StreamBridgeConfig` 类：

```python
class StreamBridgeConfig(BaseModel):
    type: Literal["memory"] = Field(default="memory", description="Stream bridge backend type")
    queue_maxsize: int = Field(default=256, description="Maximum size of the internal event queue")
```

2. 在 `AppConfig` 中删除字段：

```python
stream_bridge: StreamBridgeConfig = Field(default_factory=StreamBridgeConfig)
```

修改 `config.yaml`：删除以下段：

```yaml
# ---------------------------------------------------------------------------
# 流桥接器
# ---------------------------------------------------------------------------
# 桥接 agent 运行与连接客户端之间的流式事件。
stream_bridge:
  type: memory
  queue_maxsize: 256
```

修改 `config.test.yaml`：删除以下段：

```yaml
stream_bridge:
  type: memory
  queue_maxsize: 256
```

- [x] **Step 4: 运行全量后端测试确认通过**

```bash
pytest -v
```

Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/scaffold/infra/config/app_config.py config.yaml config.test.yaml
git commit -m "refactor(runtime): remove StreamBridge, worker and stream_bridge config"
```

---

### Task 5: 前端 — 使用 `@ag-ui/client` 替换 API 客户端

**Files:**
- Modify: `src/web/src/api.ts`
- Test: `cd src/web && npm run build`

**Interfaces:**
- Consumes: `HttpAgent`、`AgentSubscriber`、`Message` from `@ag-ui/client`
- Produces: `createAgent(threadId, url)`、`sendAgentMessage(agent, content, subscriber)`、`listAgents()`、`listTools()`、`DisplayItem` 类型

- [x] **Step 1: 重写 api.ts**

```typescript
import { HttpAgent, type AgentSubscriber, type Message } from '@ag-ui/client'

export type { Message, AgentSubscriber }

export interface DisplayItem {
  id: string
  type: 'text' | 'reasoning' | 'tool' | 'error'
  role?: 'user' | 'assistant'
  content?: string
  toolName?: string
  args?: string
  result?: string
}

export function createAgent(threadId: string, url = '/agent'): HttpAgent {
  return new HttpAgent({ url, threadId })
}

export async function sendAgentMessage(
  agent: HttpAgent,
  content: string,
  subscriber: AgentSubscriber,
): Promise<void> {
  agent.addMessage({
    id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role: 'user',
    content,
  })
  await agent.runAgent({ runId: `run-${Date.now()}` }, subscriber)
}

export async function listAgents(): Promise<{ agents: Array<{ name: string; type: string }> }> {
  const res = await fetch('/api/agents/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listTools(): Promise<{ tools: Array<{ name: string; description?: string }> }> {
  const res = await fetch('/api/tools/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
```

- [x] **Step 2: 运行构建确认类型检查通过**

```bash
cd src/web && npm run build
```

Expected: PASS（无 TypeScript 错误）

- [x] **Step 3: 提交**

```bash
git add src/web/src/api.ts
git commit -m "feat(web): replace SSE fetch client with @ag-ui/client HttpAgent"
```

---

### Task 6: 前端 — 迁移 App 与 Chat 组件到 ag-ui 事件模型

**Files:**
- Modify: `src/web/src/App.tsx`
- Modify: `src/web/src/components/Chat.tsx`
- Test: `cd src/web && npm run build`

**Interfaces:**
- Consumes: `createAgent`、`sendAgentMessage`、`DisplayItem` from `src/web/src/api.ts`
- Produces: React 状态由 `RUN_STARTED`、`TEXT_MESSAGE_*`、`REASONING_*`、`TOOL_CALL_*`、`RUN_ERROR`、`RUN_FINISHED` 事件驱动

- [x] **Step 1: 重写 App.tsx**

```tsx
import { useMemo, useState } from 'react'
import Chat from './components/Chat'
import MessageInput from './components/MessageInput'
import Sidebar from './components/Sidebar'
import ConfigPanel from './components/ConfigPanel'
import { createAgent, sendAgentMessage, type DisplayItem } from './api'

export default function App() {
  const [threadId] = useState(() => `thread-${Date.now()}`)
  const agent = useMemo(() => createAgent(threadId), [threadId])
  const [items, setItems] = useState<DisplayItem[]>([])
  const [assistantId, setAssistantId] = useState('default')
  const [isLoading, setIsLoading] = useState(false)

  const handleSend = async (text: string) => {
    const userItem: DisplayItem = {
      id: `msg-${Date.now()}`,
      type: 'text',
      role: 'user',
      content: text,
    }
    setItems((prev) => [...prev, userItem])
    setIsLoading(true)

    let currentAssistantId: string | null = null
    let currentReasoningId: string | null = null
    let currentToolId: string | null = null

    try {
      await sendAgentMessage(agent, text, {
        onTextMessageStartEvent: ({ event }) => {
          currentAssistantId = event.messageId
          setItems((prev) => [
            ...prev,
            { id: event.messageId, type: 'text', role: 'assistant', content: '' },
          ])
        },
        onTextMessageContentEvent: ({ event }) => {
          if (!currentAssistantId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentAssistantId && item.type === 'text'
                ? { ...item, content: item.content + event.delta }
                : item,
            ),
          )
        },
        onTextMessageEndEvent: () => {
          currentAssistantId = null
        },
        onReasoningStartEvent: ({ event }) => {
          currentReasoningId = event.messageId
          setItems((prev) => [
            ...prev,
            { id: event.messageId, type: 'reasoning', content: '' },
          ])
        },
        onReasoningMessageContentEvent: ({ event }) => {
          if (!currentReasoningId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentReasoningId && item.type === 'reasoning'
                ? { ...item, content: item.content + event.delta }
                : item,
            ),
          )
        },
        onReasoningEndEvent: () => {
          currentReasoningId = null
        },
        onToolCallStartEvent: ({ event }) => {
          currentToolId = event.toolCallId
          setItems((prev) => [
            ...prev,
            {
              id: event.toolCallId,
              type: 'tool',
              toolName: event.toolCallName,
              args: '',
            },
          ])
        },
        onToolCallArgsEvent: ({ toolCallBuffer }) => {
          if (!currentToolId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentToolId && item.type === 'tool'
                ? { ...item, args: toolCallBuffer }
                : item,
            ),
          )
        },
        onToolCallResultEvent: ({ event }) => {
          if (!currentToolId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentToolId && item.type === 'tool'
                ? { ...item, result: event.result }
                : item,
            ),
          )
          currentToolId = null
        },
        onRunErrorEvent: ({ event }) => {
          setItems((prev) => [
            ...prev,
            { id: `err-${Date.now()}`, type: 'error', content: event.message },
          ])
        },
      })
    } catch (err) {
      setItems((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, type: 'error', content: (err as Error).message },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar assistantId={assistantId} setAssistantId={setAssistantId} />
      <div className="flex-1 flex flex-col">
        <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
          <h1 className="font-semibold text-gray-800">DeepAgents Scaffold</h1>
          <span className="text-sm text-gray-500">Agent: {assistantId}</span>
        </header>
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col p-4">
            <Chat items={items} isLoading={isLoading} />
            <MessageInput onSend={handleSend} disabled={isLoading} />
          </div>
          <ConfigPanel />
        </div>
      </div>
    </div>
  )
}
```

- [x] **Step 2: 重写 Chat.tsx**

```tsx
import { useEffect, useRef } from 'react'
import { type DisplayItem } from '../api'

interface ChatProps {
  items: DisplayItem[]
  isLoading: boolean
}

export default function Chat({ items, isLoading }: ChatProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [items])

  return (
    <div className="flex-1 flex flex-col bg-white rounded-lg shadow overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {items.map((item) => (
          <div
            key={item.id}
            className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {item.type === 'tool' ? (
              <div className="max-w-[80%] w-full rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-2">
                <div className="text-xs font-medium text-yellow-800 mb-1">
                  Tool: {item.toolName}
                </div>
                <pre className="text-xs text-yellow-900 whitespace-pre-wrap">{item.args}</pre>
                {item.result && (
                  <div className="mt-2 text-xs text-green-700 border-t border-yellow-200 pt-2">
                    Result: {item.result}
                  </div>
                )}
              </div>
            ) : (
              <div
                className={`max-w-[70%] rounded-lg px-4 py-2 whitespace-pre-wrap ${
                  item.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : item.type === 'error'
                    ? 'bg-red-100 text-red-900'
                    : item.type === 'reasoning'
                    ? 'bg-purple-50 text-purple-900 border border-purple-200'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                <div className="text-xs opacity-70 mb-1 font-medium">
                  {item.role === 'user'
                    ? 'You'
                    : item.type === 'reasoning'
                    ? 'Reasoning'
                    : item.type === 'error'
                    ? 'Error'
                    : 'Agent'}
                </div>
                {item.content}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-4 py-2 text-sm text-gray-500">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
```

- [x] **Step 3: 运行构建确认通过**

```bash
cd src/web && npm run build
```

Expected: PASS

- [x] **Step 4: 提交**

```bash
git add src/web/src/App.tsx src/web/src/components/Chat.tsx
git commit -m "feat(web): drive UI state from ag-ui events"
```

---

### Task 7: 前端 — 移除 Vanilla JS 与 PoC 产物

**Files:**
- Delete: `src/web/static/` 目录
- Delete: `src/web/poc.html`
- Delete: `src/web/src/poc.tsx`
- Delete: `src/scaffold/api/ag_ui_poc.py`
- Modify: `src/scaffold/api/app.py`
- Modify: `src/web/index.html`
- Test: `cd src/web && npm run build`

**Interfaces:**
- Consumes: 无
- Produces: `index.html` 为 Vite/React 入口；后端不再挂载 `/static`

- [x] **Step 1: 重写 index.html 为 Vite 入口**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DeepAgents Scaffold</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [x] **Step 2: 修改 app.py 移除 static 挂载与根路由**

修改 `src/scaffold/api/app.py`：

1. 删除 `from fastapi.responses import FileResponse`
2. 删除 `from fastapi.staticfiles import StaticFiles`
3. 删除整个静态前端挂载块：

```python
    # 静态前端
    _web_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web")
    _web_dir = os.path.abspath(_web_dir)
    if os.path.isdir(_web_dir):
        app.mount("/static", StaticFiles(directory=os.path.join(_web_dir, "static")), name="static")

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(os.path.join(_web_dir, "index.html"))
    else:
        logger.warning("Frontend web directory not found at %s", _web_dir)
```

- [x] **Step 3: 删除旧产物**

```bash
git rm -r src/web/static
```

```bash
git rm src/web/poc.html src/web/src/poc.tsx src/scaffold/api/ag_ui_poc.py
```

- [x] **Step 4: 运行构建确认通过**

```bash
cd src/web && npm run build
```

Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/web/index.html src/scaffold/api/app.py
git commit -m "feat(web): remove vanilla JS frontend and PoC artifacts"
```

---

### Task 8: 集成验证与文档清理

**Files:**
- Modify: `src/scaffold/CLAUDE.md`
- Modify: `src/web/CLAUDE.md`
- Test: 完整后端测试 + 前端构建 + 手动 curl + 浏览器验证

**Interfaces:**
- Consumes: 前述全部改动
- Produces: 通过 `ruff`、后端测试、前端构建；文档与实现一致

- [x] **Step 1: 更新后端文档**

修改 `src/scaffold/CLAUDE.md`：

1. 在项目结构图中删除 `runtime/` 下的 StreamBridge/Worker 描述（保留 `runtime/` 目录说明或标记为空包）。
2. 在「核心模块说明」中删除 `runtime/worker.py` 与 `runtime/stream_bridge/` 小节。
3. 在「关键数据流」中把步骤 5-7 替换为：

```
5. handler 通过 deps.py 获取 checkpointer
6. core/agents.py:create_agent() 构建 DeepAgents agent
7. ag-ui-langgraph 将 graph 包装为 LangGraphAgent 并暴露 /agent SSE 端点
```

- [x] **Step 2: 更新前端文档**

修改 `src/web/CLAUDE.md`：

1. 删除「两套并行的前端实现」章节中关于 Vanilla JS 的全部描述。
2. 更新项目结构，删除 `static/` 目录。
3. 更新「数据流」为：

```
用户输入 (MessageInput)
    |
    v
App.tsx (sendAgentMessage)
    |
    v
api.ts -> HttpAgent -> POST /agent (SSE)
    |
    v
Backend ag-ui-langgraph /agent endpoint
    |
    v
ag-ui events <-- @ag-ui/client callbacks <-- App.tsx state updates
    |
    v
Chat.tsx (渲染消息 / reasoning / 工具调用)
```

4. 更新 `src/api.ts` 说明为 `createAgent()`、`sendAgentMessage()`、`listAgents()`、`listTools()`。

- [x] **Step 3: 代码检查与格式化**

```bash
ruff check src tests && ruff format src tests
```

Expected: PASS（无格式或 lint 错误）

- [x] **Step 4: 运行后端全量测试**

```bash
pytest -v
```

Expected: PASS

- [x] **Step 5: 前端生产构建**

```bash
cd src/web && npm run build
```

Expected: PASS

- [x] **Step 6: 启动开发服务并验证接口**

```bash
bash scripts/dev.sh
```

等待服务启动后执行：

```bash
curl -s http://localhost:8000/health
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "threadId": "thread-verify-001",
    "runId": "run-verify-001",
    "messages": [{"id": "msg-001", "role": "user", "content": "hello"}],
    "state": {},
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```

Expected: `/health` 返回 `{"status":"healthy"}`；SSE 流中包含 `RUN_STARTED`、`TEXT_MESSAGE_CONTENT`、`RUN_FINISHED`。

- [x] **Step 7: 浏览器验证前端**

访问 `http://localhost:3000`：

1. 发送一条消息，确认流式 assistant 回复正常显示。
2. 发送可触发工具调用的消息（如 "请列出当前目录文件"），确认工具调用卡片展示工具名与参数。
3. 在同一会话中发送 "我刚才说了什么"，确认 `threadId` 复用、上下文连续。

- [x] **Step 8: 停止开发服务并提交**

```bash
bash scripts/stop_dev.sh
```

```bash
git add src/scaffold/CLAUDE.md src/web/CLAUDE.md
git commit -m "docs: update CLAUDE.md for ag-ui migration"
```

---

## Self-Review

### 1. Spec coverage

- **后端协议改为 ag-ui**：Task 1 实现 `src/scaffold/api/ag_ui.py` 注册 `/agent`。
- **注册时机在 lifespan `create_agent` 之后**：Task 1 中 `register_ag_ui_endpoints(app)` 保留在 lifespan 的 `create_agent` 调用之后。
- **多 agent 支持**：Task 1 的 `register_ag_ui_endpoints` 遍历 `list_agents()`，单 agent 时为 `/agent`，多 agent 时为 `/agent/{name}`。
- **移除 `/api/runs/stream` 与 StreamBridge/run_worker**：Task 2 删除 `runs.py` 并清理 `deps.py`；Task 4 删除 `stream_bridge/` 与 `worker.py`。
- **前端使用 `@ag-ui/client` HttpAgent**：Task 5 重写 `api.ts`。
- **前端按 ag-ui 事件驱动 UI**：Task 6 重写 `App.tsx` 与 `Chat.tsx`，覆盖 `TEXT_MESSAGE_*`、`REASONING_*`、`TOOL_CALL_*`、`RUN_ERROR`。
- **移除 Vanilla JS**：Task 7 删除 `src/web/static/`、`poc.html`、`poc.tsx`。
- **`threadId`/`runId` 由前端维护**：Task 6 的 `App.tsx` 生成并复用 `threadId`，每次请求生成新 `runId`。
- **依赖安装**：`ag-ui-langgraph` 与 `@ag-ui/client` 已在 PoC 阶段加入 `pyproject.toml` 与 `package.json`；Task 8 的验证流程会重新安装锁定。
- **配置清理**：Task 4 从 `app_config.py`、`config.yaml`、`config.test.yaml` 移除 `stream_bridge`。

### 2. Placeholder scan

- 无 "TBD"、"TODO"、"implement later"。
- 无 "Add appropriate error handling" 等模糊描述。
- 每个改代码步骤都包含完整代码块。
- 无未定义的类型/函数引用。

### 3. Type consistency

- 后端：`register_ag_ui_endpoints(app: Any) -> None` 与 `app.py` 中的调用一致。
- 前端：`DisplayItem` 在 `api.ts` 定义，被 `App.tsx` 与 `Chat.tsx` 导入；`sendAgentMessage(agent: HttpAgent, content: string, subscriber: AgentSubscriber)` 签名与 `App.tsx` 调用一致。
- 事件回调字段（`event.messageId`、`event.delta`、`event.toolCallId`、`event.toolCallName`、`toolCallBuffer`、`event.result`、`event.message`）均来自 `@ag-ui/client` 的 `AgentSubscriber` 类型定义。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-11-ag-ui-langgraph-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

**Which approach?**
