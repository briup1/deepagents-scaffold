# 设计文档：迁移至 ag-ui 协议与 LangGraph 原生集成

- **日期**：2026-07-11
- **状态**：PoC 已完成，待全面实施
- **决策**：采用方案 A（彻底替换）

## 1. 背景与目标

当前 `deepagents-scaffold` 后端通过自定义 `StreamBridge` + `runs.py` SSE 端点向前端推送事件，前端 React 与 Vanilla JS 两套实现都手工解析 SSE 帧。该方案存在以下问题：

1. 协议私有，前端需要维护复杂的 SSE 解析逻辑。
2. 事件格式与 LangGraph Platform API 强耦合，扩展人机协作（HITL）、状态同步、工具调用展示困难。
3. 前后端契约不标准，难以复用社区生态。

本设计目标：**使用 ag-ui 开放协议彻底替代现有前后端通信**，后端通过 `ag_ui_langgraph` 直接暴露 LangGraph graph，前端通过 `@ag-ui/client` 消费事件流。

## 2. 关键决策

- **后端协议**：ag-ui（基于 SSE 的事件协议）。
- **后端集成方式**：`ag-ui-langgraph` 的 `add_langgraph_fastapi_endpoint(app, agent, "/agent")`，其中 `agent` 为 `LangGraphAgent(name=..., graph=graph)`。
- **前端 SDK**：`@ag-ui/client` 的 `HttpAgent`。
- **重要 PoC 发现**：`ag-ui-langgraph` 已发布至 PyPI（当前 0.0.42），`LangGraphAgent` 可成功包装 DeepAgents 编译后的 graph；但 `/agent` 端点必须在 `create_agent("default", checkpointer=...)` 完成后注册，因此注册逻辑需放在 lifespan 内，而非 `create_app()` 中。
- **替换范围**：
  - 后端：移除 `/api/runs/stream` 自定义 SSE 端点及 `StreamBridge`、`run_worker` 相关发布逻辑。
  - 前端：同时替换 React 版本（`src/web/src/`）与 Vanilla JS 版本（`src/web/static/`）。
- **保留内容**：健康检查、Agent/Tool 元数据端点、配置系统、模型工厂、工具注册、中间件链。

## 3. 架构设计

### 3.1 后端架构

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/health │  │ /api/agents │  │ /agent (ag-ui SSE)  │  │
│  │ /api/tools  │  │ /api/threads│  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                          │                                  │
│              add_langgraph_fastapi_endpoint                 │
│                          │                                  │
│                   LangGraphAgent                            │
│                          │                                  │
│              DeepAgents create_deep_agent                   │
│              (模型 + 工具 + 中间件 + 记忆)                    │
└─────────────────────────────────────────────────────────────┘
```

- `src/scaffold/api/ag_ui.py`：新建模块，负责把 `core/agents.py` 编译好的 graph 注册为 ag-ui 端点。
  - 单 agent 场景：仅注册 `/agent`，包装 `get_agent("default")`。
  - 多 agent 场景：遍历 `list_agents()`，为每个 agent 调用 `add_langgraph_fastapi_endpoint(app, LangGraphAgent(name=..., graph=graph), f"/agent/{name}")`。
- `src/scaffold/api/app.py`：在 lifespan 内（`create_agent("default")` 成功之后）引入 `ag_ui` 注册逻辑；正式迁移时移除 `runs` router。
- `src/scaffold/api/routers/runs.py`：删除。
- `src/scaffold/runtime/stream_bridge/` 与 `src/scaffold/runtime/worker.py`：移除主流程依赖，若其他模块引用则清理或重构。

### 3.1.1 注册时机约束

`add_langgraph_fastapi_endpoint` 需要 `LangGraphAgent` 实例，而后者依赖已完成编译的 graph。由于 `create_agent("default", checkpointer=app.state.checkpointer)` 在 lifespan 的 `scaffold_runtime` 上下文中执行，ag-ui 端点注册必须放在 `create_agent` 之后、 lifespan `yield` 之前。

### 3.2 前端架构

#### React 版本

```
App.tsx
  ├─ Sidebar (agent 选择)
  ├─ Chat (消息列表)
  │    ├─ TextMessage
  │    └─ ToolCallCard
  ├─ MessageInput
  └─ ConfigPanel (工具列表)

api.ts
  └─ HttpAgent (@ag-ui/client)
       └─ POST /agent (SSE)
```

- `src/web/src/api.ts`：封装 `HttpAgent`，提供 `sendMessageStream`。
- `src/web/src/App.tsx`：通过 ag-ui 事件回调驱动 UI 状态。
- `src/web/src/components/`：新增/改造 `ToolCallCard` 等组件。

#### Vanilla JS 版本

- `src/web/static/app.js`：使用原生 `EventSource` 消费 `/agent`（`@ag-ui/client` 未提供 UMD/IIFE 构建，无法直接通过 `<script>` 标签引入）。
- `src/web/static/style.css`：保持现有暗色主题，适配新的事件驱动渲染。

## 4. 数据流与事件映射

### 4.1 请求体

实测最小可用请求体如下（`messages` 中每条消息必须包含 `id`，否则 FastAPI 校验失败）：

```json
{
  "threadId": "thread_123",
  "runId": "run_001",
  "messages": [
    { "id": "msg_001", "role": "user", "content": "hello" }
  ],
  "state": {},
  "tools": [],
  "context": [],
  "forwardedProps": {}
}
```

- `threadId`、`runId` 由前端生成并传入；后端不会自动创建新 thread。
- `state`、`tools`、`context`、`forwardedProps` 在当前版本中可传空值，但字段需要存在以满足 schema。 

### 4.2 SSE 事件示例

实际流中除标准消息事件外，还会产生大量 `RAW`（LangGraph 原始事件）、`STEP_STARTED/FINISHED`、`STATE_SNAPSHOT`、`MESSAGES_SNAPSHOT` 等事件。前端可按需消费，未识别事件可忽略。

```text
data: {"type":"RUN_STARTED","threadId":"thread_123","runId":"run_001"}

data: {"type":"RAW","event":{"event":"on_chain_start",...}}

data: {"type":"STEP_STARTED","stepName":"SkillsMiddleware.before_agent"}

data: {"type":"REASONING_START","messageId":"reasoning_001"}

data: {"type":"REASONING_MESSAGE_START","messageId":"reasoning_001","role":"reasoning"}

data: {"type":"REASONING_MESSAGE_CONTENT","messageId":"reasoning_001","delta":"The user..."}

data: {"type":"TEXT_MESSAGE_START","messageId":"msg_001","role":"assistant"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"msg_001","delta":"Hello"}

data: {"type":"TEXT_MESSAGE_END","messageId":"msg_001"}

data: {"type":"MESSAGES_SNAPSHOT","messages":[...]}

data: {"type":"RUN_FINISHED","threadId":"thread_123","runId":"run_001"}
```

### 4.3 UI 事件映射

| ag-ui 事件 | 行为 |
|------------|------|
| `RUN_STARTED` | 显示加载/思考指示器 |
| `REASONING_START` / `REASONING_MESSAGE_START` | 显示推理/思考占位区域 |
| `REASONING_MESSAGE_CONTENT` | 追加 `delta` 到当前 reasoning 消息 |
| `REASONING_MESSAGE_END` | 结束当前 reasoning 展示 |
| `TEXT_MESSAGE_START` | 在消息列表末尾创建 assistant 占位消息 |
| `TEXT_MESSAGE_CONTENT` | 追加 `delta` 到当前 assistant 消息 |
| `TEXT_MESSAGE_END` | 结束当前消息，隐藏思考指示器 |
| `TOOL_CALL_START` | 渲染工具调用卡片，显示工具名 |
| `TOOL_CALL_ARGS` | 更新工具参数 JSON |
| `TOOL_CALL_END` | 标记工具调用完成 |
| `TOOL_CALL_RESULT` | 展示工具返回结果 |
| `RUN_ERROR` | 渲染错误消息 |
| `RUN_FINISHED` + `outcome.type === "interrupt"` | 弹出人类确认/输入框 |
| `RAW` / `STEP_STARTED` / `STEP_FINISHED` / `STATE_SNAPSHOT` / `MESSAGES_SNAPSHOT` | 可选调试或状态同步，未识别时可忽略 |

### 4.4 多轮对话状态

前端负责生成并维护 `threadId` 与 `runId`：
- `threadId`：会话级标识。首次对话即由前端生成并传入；后续同一对话复用该 `threadId`，后端 checkpointer 据此恢复历史状态，实现上下文连续。
- `runId`：每次请求重新生成，用于区分同一会话内的不同运行。

PoC 已验证：只要 `threadId` 不变且后端使用持久化 checkpointer，连续调用 `/agent` 可自然继承前文。

## 5. 依赖变更

### 5.1 Python 依赖

```bash
uv add "ag-ui-langgraph>=0.0.42"
```

> PoC 验证：`ag-ui-langgraph` 已发布至 PyPI，直接通过 `uv add` 安装即可，无需额外引入 `ag-ui-core`。锁定版本号避免接口漂移。

### 5.2 前端依赖

```bash
cd src/web && npm install @ag-ui/client
```

## 6. 文件变更清单

### 新增

- `src/scaffold/api/ag_ui.py`（PoC 中临时为 `ag_ui_poc.py`，迁移时重命名/整合）

### 修改

- `src/scaffold/api/app.py`：在 lifespan 内 `create_agent` 之后注册 ag-ui 端点；正式迁移时移除 `runs` router。
- `src/scaffold/api/deps.py`：清理 `stream_bridge` 依赖（若不再使用）。
- `src/web/src/api.ts`：改为 `HttpAgent`。
- `src/web/src/App.tsx`：改为 ag-ui 事件驱动。
- `src/web/src/components/Chat.tsx`：支持 reasoning、工具调用卡片。
- `src/web/static/app.js`：改为原生 `EventSource` 消费 `/agent`。
- `src/web/package.json`：添加 `@ag-ui/client`。
- `src/web/vite.config.ts`：添加 `/agent` 代理。
- `pyproject.toml` / `uv.lock`：添加并锁定 `ag-ui-langgraph`。

### PoC 临时文件（迁移时清理或移除）

- `src/scaffold/api/ag_ui_poc.py`
- `src/web/poc.html`
- `src/web/src/poc.tsx`

### 删除

- `src/scaffold/api/routers/runs.py`
- `src/scaffold/runtime/stream_bridge/base.py`
- `src/scaffold/runtime/stream_bridge/memory.py`（若存在）
- `src/scaffold/runtime/worker.py` 中与 StreamBridge 相关的发布逻辑

### 测试

- 更新 `tests/test_api.py`、`tests/e2e/test_api_runs.py` 等依赖 `/api/runs/stream` 的测试。
- 新增 ag-ui 端点的集成测试。

## 7. 验证计划

1. **安装依赖**
   ```bash
   uv pip install -e ".[dev]"
   cd src/web && npm install
   ```

2. **代码检查**
   ```bash
   ruff check src tests && ruff format src tests
   cd src/web && npm run build
   ```

3. **后端测试**
   ```bash
   pytest
   ```

4. **启动服务**
   ```bash
   bash scripts/dev.sh
   ```

5. **接口验证**
   ```bash
   curl -s http://localhost:8000/health
   curl -N -X POST http://localhost:8000/agent \
     -H "Content-Type: application/json" \
     -d '{
       "threadId": "thread_123",
       "runId": "run_001",
       "messages": [{"id": "msg_001", "role": "user", "content": "hello"}],
       "state": {},
       "tools": [],
       "context": [],
       "forwardedProps": {}
     }'
   ```

6. **前端验证**
   - 访问 `http://localhost:3000`
   - 发送消息，确认流式回复正常。
   - 触发工具调用，确认工具卡片展示正常。

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| `ag-ui-langgraph` 未发布或 API 不稳定 | 安装失败或接口变更 | 先确认 PyPI/GitHub 可用版本；锁定版本号 |
| DeepAgents 编译的 graph 与 `LangGraphAgent` 不兼容 | 端点无法正常工作 | 在小范围 PoC 验证后再全面替换 |
| 现有测试大量依赖旧端点 | 改造工作量大 | 同步更新测试，保留健康检查等无关测试 |
| 前端状态管理复杂度上升 | 工具调用/中断态处理困难 | 按 ag-ui 事件类型拆分组件职责 |

## 9. 后续可扩展

- 支持 ag-ui 的 `interrupt` 人机协作。
- 支持多模态消息（图片、文件）。
- 接入 ag-ui 调试与可观测工具。

## 10. PoC 实测结论

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `ag-ui-langgraph` 安装 | 通过 | PyPI 已发布 0.0.42，`uv add` 直接可用 |
| `LangGraphAgent` 包装 DeepAgents graph | 通过 | `LangGraphAgent(name="default", graph=get_agent("default"))` 成功 |
| `/agent` 端点暴露 | 通过 | `add_langgraph_fastapi_endpoint(app, agent, "/agent")` 正常注册 |
| 注册时机 | 约束 | 必须在 lifespan 内 `create_agent("default", checkpointer=...)` 之后注册 |
| 前端 `@ag-ui/client` | 通过 | `HttpAgent` 通过回调式 `AgentSubscriber` 消费事件，`runAgent()` 返回 Promise |
| 请求体验证 | 通过 | `messages` 数组中每条消息必须带 `id`，否则 FastAPI 报 `Field required` |
| 事件流完整性 | 通过 | 除文本/工具事件外，还收到 `RAW`、`STEP_*`、`REASONING_*`、`MESSAGES_SNAPSHOT` 等 |
| 多轮连续性 | 通过 | 复用同一 `threadId` 时，后端 checkpointer 能恢复上下文 |
| Vanilla JS 集成 | 可行 | `@ag-ui/client` 无 UMD/IIFE 构建，建议使用原生 `EventSource` 直接消费 `/agent` |

**关键代码片段（PoC 后端）**：

```python
# src/scaffold/api/ag_ui_poc.py
from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from scaffold.core.agents import get_agent

def register_ag_ui_endpoint(app):
    agent = LangGraphAgent(name="default", graph=get_agent("default"))
    add_langgraph_fastapi_endpoint(app, agent, "/agent")
```

```python
# src/scaffold/api/app.py 的 lifespan 内
async with scaffold_runtime(app):
    create_agent(name="default", checkpointer=app.state.checkpointer)
    register_ag_ui_endpoint(app)
    yield
```

**关键代码片段（PoC 前端）**：

```tsx
const agent = new HttpAgent({ url: '/agent', threadId })
agent.addMessage({ id: `msg-${Date.now()}`, role: 'user', content: input })
await agent.runAgent(
  { runId: `poc-run-${Date.now()}` },
  {
    onRunStartedEvent: ({ event }) => { ... },
    onTextMessageContentEvent: ({ event }) => { ... },
    onToolCallStartEvent: ({ event }) => { ... },
    onRunFinishedEvent: () => { ... },
    onRunErrorEvent: ({ event }) => { ... },
  },
)
```

基于以上结论，本设计文档已相应更新，后续可按第 6 章清单全面实施。
