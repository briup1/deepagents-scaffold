# 对话历史功能设计文档

**日期**：2026-08-18  
**主题**：为 DeepAgents Scaffold 增加对话历史（Conversation History）功能  
**方案**：方案 B —— 新增独立 `messages` 表  
**作者**：Claude Code  
**状态**：待评审  

---

## 1. 背景与目标

当前系统的前端只有“新建会话”和 Agent 切换，没有历史会话列表。后端虽然已经有：

- `AsyncSqliteSaver` 检查点器（`src/scaffold/api/deps.py`）
- `/api/threads` 线程元数据接口（`src/scaffold/api/routers/threads.py`）
- `/api/threads/{thread_id}/state` 状态接口（`src/scaffold/api/routers/state.py`）
- AG-UI `/agent` SSE 端点（`src/scaffold/api/ag_ui.py`）

但缺少：

1. 历史会话列表查询接口；
2. 可读的会话标题；
3. 前端把历史消息加载回聊天界面的能力；
4. 独立的、结构化的消息持久化层。

### 1.1 目标

- 用户可以在左侧边栏看到历史会话列表；
- 点击历史会话后，前端加载该会话的全部历史消息并渲染；
- 新消息自动持久化，后端重启后历史不丢失；
- 会话标题自动生成或更新；
- 不同 Agent 的历史相互隔离；
- 不破坏现有 AG-UI SSE 流式接口行为。

### 1.2 非目标

- 多用户隔离（当前系统无用户体系，历史按 `thread_id` 全局可见）；
- 消息编辑、删除单条消息、分支对话（thread fork）；
- 文件/图片附件历史；
- 全文搜索历史内容。

---

## 2. 方案选型

| 维度 | 方案 A：从 checkpoint 反解 | 方案 B：独立 `messages` 表（选中） |
|------|---------------------------|----------------------------------|
| 存储位置 | 复用 `checkpoints.db` | 新建 `history.db`（位于 `database.sqlite_dir`） |
| 数据稳定性 | 依赖 LangGraph 内部 checkpoint 结构，SDK 升级可能 breakage | 基于稳定的 AG-UI 消息协议，向后兼容 |
| 查询性能 | 需要反解整个 checkpoint 才能拿到消息 | 按 `thread_id` 索引直接查询 |
| 标题/预览 | 需要从 checkpoint 解析最后一条消息 | 可直接查询 `threads` 表和 `messages` 表 |
| 写入复杂度 | 不需要额外写路径 | 需要在 AG-UI endpoint 中拦截并写入 |
| 冗余度 | 无冗余 | 与 checkpoint 有轻微冗余 |
| 适用场景 | 快速原型、内部工具 | 生产系统、长期维护 |

**选择方案 B 的理由**：AG-UI 消息格式是前后端之间的稳定契约，独立消息表让历史功能与 LangGraph 运行时解耦，便于后续做搜索、导出、审计等扩展。

---

## 3. 数据模型

新建数据库文件 `{database.sqlite_dir}/history.db`，内部两张表：

### 3.1 `threads` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `thread_id` | `TEXT PRIMARY KEY` | 全局唯一会话 ID，与 AG-UI `threadId` 一致 |
| `agent_id` | `TEXT NOT NULL` | 该会话绑定的 Agent 名称 |
| `title` | `TEXT` | 会话标题，首次用户消息后生成 |
| `created_at` | `TEXT NOT NULL` | ISO 8601 时间戳，UTC |
| `updated_at` | `TEXT NOT NULL` | ISO 8601 时间戳，UTC |

### 3.2 `messages` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_id` | `TEXT PRIMARY KEY` | 消息唯一 ID（AG-UI message id） |
| `thread_id` | `TEXT NOT NULL` | 外键，关联 `threads.thread_id` |
| `run_id` | `TEXT` | 该消息所属的 AG-UI run id |
| `role` | `TEXT NOT NULL` | `user` / `assistant` / `system` / `tool` |
| `content` | `TEXT` | 消息文本内容 |
| `name` | `TEXT` | tool 消息中的工具名（可选） |
| `tool_call_id` | `TEXT` | tool 消息中的 tool call id（可选） |
| `tool_calls` | `TEXT` | JSON 文本，assistant 消息中的 tool calls（可选） |
| `created_at` | `TEXT NOT NULL` | ISO 8601 时间戳，UTC |

### 3.3 索引

```sql
CREATE INDEX idx_messages_thread_id ON messages(thread_id);
CREATE INDEX idx_threads_updated_at ON threads(updated_at DESC);
```

---

## 4. 后端架构

### 4.1 新增模块

```
src/scaffold/
├── infra/
│   └── history/
│       ├── __init__.py
│       ├── connection.py       # 历史库连接与生命周期
│       ├── models.py           # Pydantic 模型：Thread、Message、ThreadSummary
│       └── repository.py       # 异步 CRUD：create_thread、list_threads、
│                               # add_message、get_messages、update_title
├── api/
│   └── routers/
│       ├── threads.py          # 扩展：GET /api/threads、GET /api/threads/{id}/messages
│       └── history.py          # （可选）独立 history 路由
└── api/
    └── deps.py                 # 增加 get_history_repository 依赖
```

### 4.2 依赖注入

在 `scaffold_runtime()` 中初始化 `HistoryRepository`，存入 `app.state.history_repo`：

```python
async with aiosqlite.connect(history_db_path) as conn:
    repo = HistoryRepository(conn)
    await repo.migrate()
    app.state.history_repo = repo
```

新增依赖函数：

```python
def get_history_repo(request: Request) -> HistoryRepository:
    repo = getattr(request.app.state, "history_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="History repository not initialized")
    return repo
```

### 4.3 AG-UI endpoint 集成

在 `src/scaffold/api/ag_ui.py` 的 `langgraph_agent_endpoint()` 中：

1. **请求前置处理**：
   - 从 `input_data.messages` 提取用户消息；
   - 若 `thread_id` 在 `threads` 表中不存在，则创建线程（`agent_id = input_data.agent_id or default_name`）；
   - 将用户消息写入 `messages` 表（幂等：按 `message_id` 去重）。

2. **流式响应中**：
   - 在 `_eager_event_generator` 或 `_produce_events_to_queue` 中监听 `TEXT_MESSAGE_END` 事件；
   - 将完整的 assistant 消息写入 `messages` 表；
   - 同步更新 `threads.updated_at`。

3. **标题生成**：
   - 复用现有 `TitleMiddleware`，但将其生成的 `_thread_title` 写入 `threads.title`；
   - 若未启用 `TitleMiddleware`，则采用启发式标题（前 8 个词或 20 个字符）。

### 4.4 避免重复写入

`RunAgentInput.messages` 中可能已经包含历史消息（取决于前端行为）。写入时按 `message_id` 做 `INSERT OR IGNORE`，避免重复。

---

## 5. API 设计

### 5.1 扩展 `GET /api/threads`

列出历史会话，按 `updated_at` 倒序。

**请求**：

```http
GET /api/threads?limit=50&offset=0
```

**响应**：

```json
{
  "threads": [
    {
      "thread_id": "thread-xxx",
      "agent_id": "default",
      "title": "如何配置环境变量",
      "last_message_preview": "你可以复制 .env.example 到 .env...",
      "updated_at": "2026-08-18T14:30:00Z",
      "created_at": "2026-08-18T14:25:00Z"
    }
  ],
  "total": 12
}
```

### 5.2 扩展 `GET /api/threads/{thread_id}/messages`

返回某一会话的全部消息，按时间正序。

**响应**：

```json
{
  "thread_id": "thread-xxx",
  "messages": [
    {
      "message_id": "msg-001",
      "run_id": "run-001",
      "role": "user",
      "content": "你好",
      "created_at": "2026-08-18T14:25:10Z"
    },
    {
      "message_id": "msg-002",
      "run_id": "run-001",
      "role": "assistant",
      "content": "有什么可以帮你的？",
      "created_at": "2026-08-18T14:25:12Z"
    }
  ]
}
```

### 5.3 保留现有接口

- `POST /api/threads/`：继续创建线程，同时写入 `threads` 表；
- `GET /api/threads/{thread_id}`：继续返回线程元数据；
- `POST /agent` / `POST /agent/{agentId}`：继续作为 SSE 入口，但内部持久化消息。

---

## 6. 前端架构

### 6.1 新增 API 模块

`src/web/src/api/threads.ts`：

```ts
export interface ThreadSummary {
  thread_id: string
  agent_id: string
  title: string | null
  last_message_preview: string | null
  updated_at: string
  created_at: string
}

export interface ThreadMessage {
  message_id: string
  run_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  created_at: string
}

export async function listThreads(): Promise<{ threads: ThreadSummary[]; total: number }>
export async function getThreadMessages(threadId: string): Promise<{ thread_id: string; messages: ThreadMessage[] }>
export async function createThread(agentId: string): Promise<{ thread_id: string }>
```

### 6.2 Sidebar 扩展

在现有 `Sidebar.tsx` 中新增“历史会话”区域：

- 挂载时调用 `listThreads()`；
- 列表项显示 `title` 或 `last_message_preview`；
- 当前选中的 `thread_id` 高亮；
- 点击某条目：
  1. 调 `getThreadMessages(threadId)`；
  2. `App.tsx` 设置 `threadId` 和 `initialMessages`；
  3. 如果该历史会话的 `agent_id` 与当前不同，同步切换 Agent。

### 6.3 App.tsx 状态扩展

```ts
const [threadId, setThreadId] = useState<string>(...)
const [initialMessages, setInitialMessages] = useState<ThreadMessage[]>([])
```

点击“新建会话”时：

1. 调用 `POST /api/threads`（或延迟到第一条消息时创建）；
2. `setThreadId(newId)`；
3. `setInitialMessages([])`。

### 6.4 CopilotChat 加载历史消息

CopilotKit v2 的 `CopilotChat` 支持通过 `initialMessages` 或等效属性注入初始消息。需要在实现前确认：

- `CopilotChat` 是否接受 `initialMessages`？
- 消息格式是 AG-UI `Message` 还是 CopilotKit 内部格式？

如果 `CopilotChat` 不直接支持，则考虑：

1. 在 `ChatInner` 中调用 `useCopilotChat` 的 `setMessages` 方法（如果暴露）；
2. 或者包装 `HttpAgent`，在构造时注入历史消息。

### 6.5 空状态

当没有历史会话时，Sidebar 显示一句引导文案：

> 暂无历史会话，开始一段新对话吧。

---

## 7. 消息持久化详细流程

### 7.1 新建会话 → 第一条消息

```
用户输入 → CopilotChat → HttpAgent POST /agent/{agentId}
                                        │
                                        ▼
                         langgraph_agent_endpoint()
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            ensure_thread()      write_user_messages()   run agent
                    │                   │                   │
                    ▼                   ▼                   ▼
            INSERT threads        INSERT messages      produce events
                                                       │
                                                       ▼
                                              write_assistant_message()
                                                       │
                                                       ▼
                                               INSERT messages
                                               UPDATE threads.updated_at
```

### 7.2 继续已有会话

```
用户输入 → /agent/{agentId} with threadId
              │
              ▼
        ensure_thread() 发现已存在，跳过创建
              │
              ▼
        write_user_messages() 幂等写入
              │
              ▼
        run agent（自动从 checkpoint 恢复上下文）
              │
              ▼
        write_assistant_message()
```

### 7.3 标题生成时机

在 assistant 第一条完整回复生成后：

1. `TitleMiddleware.after_model()` 生成 `_thread_title`；
2. AG-UI endpoint 在 `RUN_FINISHED` 后读取 `_thread_title`；
3. 调用 `repo.update_title(thread_id, title)`。

如果未启用 `TitleMiddleware`，则在 `write_user_messages()` 时，若 `threads.title` 为空，用第一条用户消息生成启发式标题。

---

## 8. 错误处理

| 场景 | 处理策略 |
|------|---------|
| 历史库初始化失败 | 记录 error 日志，API 返回 503，但不应阻塞 Agent 运行 |
| 写入历史消息失败 | 记录 error，不影响 SSE 流向用户 |
| 查询历史列表失败 | 前端显示错误提示，允许重试 |
| 加载某会话消息失败 | 前端提示“无法加载历史消息”，保留当前会话 |
| thread_id 不存在 | `GET /api/threads/{id}/messages` 返回 404 |
| 消息格式不识别 | 跳过写入并记录 warning |

---

## 9. 测试策略

### 9.1 后端测试

- `tests/test_history_repository.py`：测试 `HistoryRepository` 的 CRUD、幂等写入、去重、排序。
- `tests/test_threads_api.py`：测试 `GET /api/threads` 和 `GET /api/threads/{id}/messages`。
- `tests/e2e/test_ag_ui.py` 扩展：验证发送消息后数据库中存在对应记录。

### 9.2 前端测试

- `src/web/src/api/threads.test.ts`：mock fetch 测试列表和详情接口。
- `src/web/src/components/__tests__/ThreadList.test.tsx`：测试列表渲染、点击切换、空状态。
- `App.test.tsx` 扩展：验证点击历史会话后 `threadId` 和 `initialMessages` 更新。

### 9.3 验证命令

```bash
# 后端
ruff check src tests && ruff format src tests
pytest tests/test_history_repository.py tests/test_threads_api.py tests/e2e/test_ag_ui.py -v

# 前端
cd src/web && npm run build
cd src/web && npm test

# 端到端
bash scripts/dev.sh
# 发送消息 -> 调 GET /api/threads -> 调 GET /api/threads/{id}/messages
```

---

## 10. 迁移与回滚

### 10.1 数据库迁移

`history.db` 是新建文件，无需迁移旧数据。首次启动时 `HistoryRepository.migrate()` 自动建表。

### 10.2 配置变更

可选：在 `config.yaml` 的 `database` 段增加历史库路径：

```yaml
database:
  sqlite_dir: data
  history_db: data/history.db   # 新增，可选，默认由 sqlite_dir 推导
```

若未配置，默认使用 `{sqlite_dir}/history.db`。

### 10.3 回滚

若功能出现问题，可通过 config 开关禁用历史持久化：

```yaml
history:
  enabled: true   # 默认 true
```

禁用后 AG-UI endpoint 跳过写入，但列表接口返回空。

---

## 11. 接口契约

### 前后端新增契约

| 端点 | 方法 | 请求 | 响应 |
|------|------|------|------|
| `/api/threads` | GET | `limit`, `offset` query | `{threads: ThreadSummary[], total: number}` |
| `/api/threads/{id}/messages` | GET | path `id` | `{thread_id, messages: ThreadMessage[]}` |
| `/api/threads` | POST | `{thread_id?, agent_id?}` | `{thread_id, metadata}` |

### AG-UI 协议不变

`POST /agent` 和 `POST /agent/{agentId}` 的请求/响应格式保持不变。历史持久化对前端透明。

---

## 12. 待确认事项

在实现前需要确认以下几点：

1. **CopilotChat 历史消息注入方式**：`CopilotChat` 是否支持 `initialMessages`？如不支持，需要调研 `useCopilotChat` 的 API。
2. **历史库位置**：使用独立 `history.db` 还是复用 `checkpoints.db`？本方案推荐独立文件。
3. **标题生成策略**：是否启用 `TitleMiddleware` 的 LLM 生成？还是先用启发式标题？
4. **新建会话时是否立即创建线程记录**：前端点击“新建会话”时立即 `POST /api/threads`，还是等第一条消息到达后端时再懒创建？
5. **多 Agent 历史隔离**：切换 Agent 时是否只显示当前 Agent 的历史？本方案建议按 `agent_id` 过滤 `GET /api/threads?agent_id=xxx`。

---

## 13. 总结

本方案通过新增独立的 `history.db`（`threads` + `messages` 表）实现对话历史功能：

- 后端在 AG-UI SSE endpoint 中透明持久化消息；
- 新增 `GET /api/threads` 和 `GET /api/threads/{thread_id}/messages`；
- 前端 Sidebar 增加历史列表，点击后加载历史消息到 `CopilotChat`；
- 会话标题由 `TitleMiddleware` 或启发式逻辑生成；
- 不影响现有 AG-UI 协议和 checkpoint 机制。

下一步：根据本设计文档编写实现计划（implementation plan）。
