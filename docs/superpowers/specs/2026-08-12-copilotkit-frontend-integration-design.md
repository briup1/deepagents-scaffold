# CopilotKit 前端集成设计

## 1. 项目背景与目标

当前 `deepagents-scaffold` 后端已通过 `ag-ui-langgraph` 暴露标准 AG-UI `/agent` SSE 端点。前端目前使用 `@ag-ui/client` 手写了聊天界面。

本设计目标：
- 用 **CopilotKit React 组件**替换现有前端聊天界面。
- 前端通过 **AG-UI 协议直连**后端 `/agent/{agentId}` 端点，不引入 CopilotKit Runtime 服务。
- 保留现有 **Agent 切换能力**。
- 第一版实现两种 **Generative UI**：Markdown 卡片、数据表格。

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (React + Vite)                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  CopilotKit Provider (runtimeUrl=/agent/{agentId})      │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  CopilotSidebar                                  │   │   │
│  │  │  ┌─────────────┐  ┌─────────────────────────┐   │   │   │
│  │  │  │ AgentSelector│  │ CopilotChat             │   │   │   │
│  │  │  └─────────────┘  │  (Generative UI render) │   │   │   │
│  │  │                   └─────────────────────────┘   │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ AG-UI Protocol (SSE /agent/{agentId})
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      后端 (FastAPI + DeepAgents)                 │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │ /api/agents/    │    │ /agent/{agentId}  (ag_ui.py)        │ │
│  │ /api/tools/     │    │  - LangGraphAgent.run()             │ │
│  │ /health         │    │  - EventEncoder (SSE)               │ │
│  └─────────────────┘    └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 核心设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 连接模式 | 前端直连 FastAPI `/agent/{agentId}` | 少一个 Runtime 服务，架构最简 |
| Agent 切换 | Sidebar 选择器动态修改 `runtimeUrl` | 复用现有 `/agent` 与 `/agent/{name}` 端点 |
| Generative UI 触发 | AG-UI 文本事件携带 `metadata.generative_ui` | 不修改 AG-UI 协议核心事件类型，兼容现有后端 |
| 组件渲染 | 前端注册 `MarkdownCard`、`DataTable` | 由 `metadata.generative_ui.type` 路由 |

## 3. 组件与模块划分

### 3.1 前端组件

| 组件/模块 | 路径 | 职责 |
|---|---|---|
| `CopilotKitProvider` | `src/web/src/App.tsx` | 包裹应用，提供 `runtimeUrl`、`threadId`、公共状态 |
| `AgentSelector` | `src/web/src/components/AgentSelector.tsx` | 下拉选择 Agent，触发 `runtimeUrl` 切换 |
| `GenerativeUIRenderer` | `src/web/src/components/GenerativeUIRenderer.tsx` | 根据 AG-UI 事件 metadata 渲染 MarkdownCard / DataTable |
| `MarkdownCard` | `src/web/src/components/ui/MarkdownCard.tsx` | 渲染富文本卡片 |
| `DataTable` | `src/web/src/components/ui/DataTable.tsx` | 渲染结构化表格 |
| `api/copilotkit.ts` | `src/web/src/api/copilotkit.ts` | 封装 `listAgents()`，供 AgentSelector 使用 |

### 3.2 后端模块

| 模块 | 路径 | 变更 |
|---|---|---|
| `scaffold.api.ag_ui` | `src/scaffold/api/ag_ui.py` | **不修改**，继续使用现有 `/agent/{name}` SSE 端点 |
| `scaffold.core.agents` | `src/scaffold/core/agents.py` | **不修改**，继续由 `config.yaml` 注册 agent |
| `config.yaml` | 根目录 | 可选：新增/调整 `showcase` 或 `code_reviewer` 的 system prompt，引导其输出结构化内容 |

### 3.3 新增、修改、删除清单

- **新增文件**：
  - `src/web/src/components/AgentSelector.tsx`
  - `src/web/src/components/GenerativeUIRenderer.tsx`
  - `src/web/src/components/ui/MarkdownCard.tsx`
  - `src/web/src/components/ui/DataTable.tsx`
  - `src/web/src/api/copilotkit.ts`
  - `src/web/src/types/generative-ui.ts`
- **修改文件**：
  - `src/web/src/App.tsx`
  - `src/web/src/package.json`
  - `src/web/src/index.css`
- **删除文件**：
  - `src/web/src/components/Chat.tsx`
  - `src/web/src/components/MessageInput.tsx`
  - `src/web/src/components/Sidebar.tsx`
  - `src/web/src/components/ConfigPanel.tsx`
  - `src/web/src/api.ts`

**说明**：后端在 Phase 1 不改动；Generative UI 的 Agent 提示词调优作为 Phase 2 的填肉任务进入 `MOCK_REGISTRY.md`。

## 4. 数据流

### 4.1 正常对话流

1. 用户打开页面。
   - `App.tsx` 生成 `threadId`，默认选中 `default` agent。
   - `CopilotKit` Provider 初始化 `runtimeUrl=/agent`。
2. 用户发送消息。
   - `CopilotChat` 通过 `runtimeUrl` 向 `/agent` 发起 POST。
   - 后端 `ag_ui.py` 启动 `LangGraphAgent.run()`。
   - SSE 事件流返回前端。
3. 前端消费事件。
   - 普通文本事件：`CopilotChat` 默认渲染。
   - 带 `metadata.generative_ui` 的文本事件：`GenerativeUIRenderer` 拦截并渲染 `MarkdownCard` / `DataTable`。
   - 工具调用事件：`CopilotChat` 默认展示。
4. 用户切换 Agent。
   - `AgentSelector` 更新状态。
   - `CopilotKit` Provider 重新挂载，`runtimeUrl=/agent/{name}`。

### 4.2 Agent 切换边界处理

- **状态重置**：切换 Agent 时，前端主动清空 CopilotKit 内部消息列表；`threadId` 保持不变，以便后端仍可按同一 thread 聚合日志。
- **连接清理**：旧的 SSE 连接由 CopilotKit 内部管理，Provider 重新挂载时自动断开。
- **错误隔离**：某个 Agent 的端点不可用只影响当前选择，不导致整个应用崩溃。

### 4.3 Generative UI 数据流

后端 Agent 输出示例：

```json
{
  "type": "TEXT_MESSAGE_CONTENT",
  "delta": "",
  "messageId": "msg-xxx",
  "metadata": {
    "generative_ui": {
      "type": "markdown_card",
      "title": "代码审查摘要",
      "content": "# ..."
    }
  }
}
```

前端处理：`GenerativeUIRenderer` 识别 `metadata.generative_ui.type`：

- `"markdown_card"` → `MarkdownCard` 组件
- `"data_table"` → `DataTable` 组件

## 5. 接口契约定义

### 5.1 前端 ↔ 后端：AG-UI 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/agent` | 单 Agent 模式（当前只有一个注册 agent 时） |
| `POST` | `/agent/{agentId}` | 多 Agent 模式（当前有多个注册 agent 时） |
| `GET`  | `/agent/health` | Agent 健康检查 |

请求体为 AG-UI `RunAgentInput` 标准结构：

```json
{
  "threadId": "thread-xxx",
  "runId": "run-xxx",
  "messages": [
    { "id": "msg-xxx", "role": "user", "content": "hello" }
  ],
  "state": {},
  "tools": [],
  "context": [],
  "forwardedProps": {}
}
```

响应为 `text/event-stream`，事件编码由后端 `EventEncoder` 决定。

### 5.2 Generative UI Metadata 契约

```typescript
// src/web/src/types/generative-ui.ts
export interface GenerativeUIMetadata {
  type: 'markdown_card' | 'data_table'
  title?: string
}

export interface MarkdownCardMetadata extends GenerativeUIMetadata {
  type: 'markdown_card'
  content: string   // Markdown 字符串
}

export interface DataTableMetadata extends GenerativeUIMetadata {
  type: 'data_table'
  columns: Array<{ key: string; label: string }>
  rows: Array<Record<string, string | number | boolean>>
}
```

### 5.3 前端内部组件契约

```typescript
// AgentSelector
interface AgentSelectorProps {
  agents: Array<{ name: string; type: string }>
  value: string
  onChange: (agentId: string) => void
}

// GenerativeUIRenderer
interface GenerativeUIRendererProps {
  metadata: GenerativeUIMetadata
}
```

### 5.4 后端不变性声明

- 不修改 `RunAgentInput` 结构。
- 不修改 SSE 事件编码格式。
- `metadata` 字段是 AG-UI 标准事件已支持的扩展字段，不引入新的事件类型。

## 6. 错误处理

| 场景 | 处理策略 |
|---|---|
| 后端 `/agent` 返回 4xx/5xx | CopilotKit 内部展示错误；前端补充全局 `ErrorBoundary` 兜底 |
| SSE 连接中断 | CopilotKit 自动重连；前端记录 `console.debug` 日志 |
| Agent 切换时旧连接未关闭 | 依赖 CopilotKit Provider 重新挂载清理 |
| Generative UI metadata 解析失败 | `GenerativeUIRenderer` 捕获异常，降级为普通文本展示 |
| 不支持的 `generative_ui.type` | 记录 warning，降级为普通文本展示 |
| 后端未返回 metadata | 走 CopilotKit 默认渲染路径 |

## 7. 测试策略

| 层级 | 测试内容 |
|---|---|
| 单元测试 | `MarkdownCard`、`DataTable`、`GenerativeUIRenderer` 的渲染与降级逻辑 |
| 集成测试 | `AgentSelector` 切换后 `runtimeUrl` 是否正确 |
| 端到端 | `bash scripts/dev.sh` 启动后，验证聊天流式响应、Agent 切换、Generative UI 渲染 |
| 契约测试 | 后端 `/agent` SSE 事件携带 metadata 的样本测试 |

## 8. 验证命令

```bash
# 后端健康检查
curl -s http://localhost:8000/health

# Agent 端点健康检查
curl -s http://localhost:8000/agent/health

# AG-UI 流式接口测试
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"thread-verify-001","runId":"run-verify-001","messages":[{"id":"msg-001","role":"user","content":"hello"}],"state":{},"tools":[],"context":[],"forwardedProps":{}}'
```

## 9. 风险与后续迭代

| 风险 | 缓解措施 |
|---|---|
| CopilotKit React UI 对自定义 AG-UI 后端的兼容性需验证 | 先做最小可运行骨架，跑通聊天流后再扩展 Generative UI |
| Generative UI 目前依赖后端 Agent 主动输出 metadata | 先用硬编码/提示词引导生成 mock 数据，再逐步替换为真实业务逻辑 |
| 删除旧组件后可能丢失 ConfigPanel 的工具展示 | 如需要，后续在 CopilotKit Sidebar 中添加工具列表面板 |

## 10. 参考

- [AG-UI Protocol](https://ag-ui.com)
- [CopilotKit Documentation](https://docs.copilotkit.ai)
- 项目内相关文件：
  - `src/scaffold/api/ag_ui.py`
  - `src/web/src/App.tsx`
  - `src/web/src/api.ts`
  - `config.yaml`
