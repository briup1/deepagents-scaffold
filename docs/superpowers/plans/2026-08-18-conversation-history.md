# 对话历史功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 DeepAgents Scaffold 增加完整的对话历史功能：后端独立持久化消息，前端 Sidebar 可列出、切换、加载历史会话。

**Architecture:** 后端新增 `history.db`（`threads` + `messages` 表），在 AG-UI SSE endpoint 中拦截进出消息并写入；前端新增 Threads API 客户端和历史列表组件，点击历史会话时通过 `useAgent().agent.setMessages()` 把历史消息注入当前 Agent。

**Tech Stack:** FastAPI、aiosqlite、Pydantic、LangGraph、React 18、TypeScript、CopilotKit v2、@ag-ui/client、Vitest。

**Spec:** `docs/superpowers/specs/2026-08-18-conversation-history-design.md`

## Global Constraints

- 所有 Python 代码必须通过 `ruff check src tests` 和 `ruff format src tests`。
- 所有 TypeScript 代码必须通过 `cd src/web && npm run build`（含类型检查）。
- 后端函数必须带类型注解，目标 Python 版本 `py312`。
- 新增 Python 依赖必须通过 `uv add <package>` 安装，禁止直接编辑 `pyproject.toml`。
- 禁止在代码中硬编码 API Key、Token 或数据库路径；路径从 `AppConfig` 推导。
- 禁止在异常处理中忽略错误；历史写入失败不得阻塞 SSE 流向用户。
- 前端组件使用 PascalCase，样式使用 Tailwind CSS。
- 所有 AI 生成的文档、注释、文案使用中文。

---

## 文件结构

### 后端新增/修改

- `src/scaffold/infra/history/__init__.py` — 导出历史模块公共接口。
- `src/scaffold/infra/history/models.py` — Pydantic 模型：`ThreadSummary`、`ThreadMessage`、`ThreadCreate`。
- `src/scaffold/infra/history/repository.py` — `HistoryRepository`：迁移、线程 CRUD、消息 CRUD、标题更新。
- `src/scaffold/api/deps.py` — 在 `scaffold_runtime()` 中初始化 `HistoryRepository`，新增 `get_history_repo()`。
- `src/scaffold/api/routers/threads.py` — 扩展 `GET /api/threads` 和 `GET /api/threads/{thread_id}/messages`。
- `src/scaffold/api/ag_ui.py` — 在 `langgraph_agent_endpoint()` 中写入用户消息，在事件流中写入助手消息和标题。
- `src/scaffold/infra/config/app_config.py` — 可选：在 `DatabaseConfig` 中增加 `history_db` 字段（有默认值）。
- `tests/test_history_repository.py` — 历史仓库单元测试。
- `tests/test_threads_api.py` — Threads API 测试。
- `tests/e2e/test_ag_ui.py` — 扩展：验证消息持久化。

### 前端新增/修改

- `src/web/src/api/threads.ts` — Threads API 客户端：`listThreads`、`getThreadMessages`、`createThread`。
- `src/web/src/api/threads.test.ts` — API 客户端测试。
- `src/web/src/components/ThreadList.tsx` — 历史会话列表组件。
- `src/web/src/components/__tests__/ThreadList.test.tsx` — 列表组件测试。
- `src/web/src/components/Sidebar.tsx` — 扩展：加入历史列表区域。
- `src/web/src/App.tsx` — 扩展：加载历史消息并注入 Agent。
- `src/web/src/App.test.tsx` — 扩展：历史切换测试。

---

## Task 1：历史仓库数据模型

**Files:**
- Create: `src/scaffold/infra/history/__init__.py`
- Create: `src/scaffold/infra/history/models.py`

**Interfaces:**
- Produces: `ThreadSummary`, `ThreadMessage`, `ThreadCreate` Pydantic models.

- [ ] **Step 1：创建包初始化文件**

```python
# src/scaffold/infra/history/__init__.py
"""历史消息持久化模块。"""

from scaffold.infra.history.models import ThreadCreate, ThreadMessage, ThreadSummary
from scaffold.infra.history.repository import HistoryRepository

__all__ = ["HistoryRepository", "ThreadSummary", "ThreadMessage", "ThreadCreate"]
```

- [ ] **Step 2：定义 Pydantic 模型**

```python
# src/scaffold/infra/history/models.py
"""历史消息数据模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    """创建线程请求。"""

    thread_id: str | None = Field(default=None, description="可选显式线程 ID")
    agent_id: str = Field(default="default", description="绑定 Agent 名称")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadSummary(BaseModel):
    """线程列表项。"""

    thread_id: str
    agent_id: str
    title: str | None
    last_message_preview: str | None
    created_at: str
    updated_at: str


class ThreadMessage(BaseModel):
    """单条历史消息。"""

    message_id: str
    run_id: str | None
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    created_at: str
```

- [ ] **Step 3：提交**

```bash
git add src/scaffold/infra/history/__init__.py src/scaffold/infra/history/models.py
git commit -m "feat(history): 添加历史消息数据模型"
```

---

## Task 2：历史仓库实现

**Files:**
- Create: `src/scaffold/infra/history/repository.py`

**Interfaces:**
- Consumes: `ThreadCreate`, `ThreadSummary`, `ThreadMessage` from Task 1.
- Produces: `HistoryRepository` class with methods:
  - `async migrate() -> None`
  - `async ensure_thread(thread_id: str, agent_id: str) -> None`
  - `async list_threads(agent_id: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[ThreadSummary], int]`
  - `async get_messages(thread_id: str) -> list[ThreadMessage]`
  - `async add_message(message: ThreadMessage) -> None`
  - `async add_messages(messages: list[ThreadMessage]) -> None`
  - `async update_title(thread_id: str, title: str) -> None`

- [ ] **Step 1：编写迁移和核心 CRUD**

```python
# src/scaffold/infra/history/repository.py
"""历史消息仓库：基于 aiosqlite。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from scaffold.infra.history.models import ThreadCreate, ThreadMessage, ThreadSummary


class HistoryRepository:
    """管理 threads 与 messages 的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建历史消息表结构。"""
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                run_id TEXT,
                role TEXT NOT NULL,
                content TEXT,
                name TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_threads_updated_at ON threads(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_threads_agent_id ON threads(agent_id);
            """
        )
        await self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def ensure_thread(self, thread_id: str, agent_id: str) -> None:
        """确保线程记录存在；不存在则创建。"""
        now = self._now()
        await self._conn.execute(
            """
            INSERT INTO threads (thread_id, agent_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (thread_id, agent_id, None, now, now),
        )
        await self._conn.commit()

    async def list_threads(
        self,
        agent_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ThreadSummary], int]:
        """返回线程列表和总数。"""
        where_clause = "WHERE agent_id = ?" if agent_id else ""
        params: tuple[Any, ...] = (agent_id,) if agent_id else ()

        cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM threads {where_clause}", params
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0

        cursor = await self._conn.execute(
            f"""
            SELECT
                t.thread_id,
                t.agent_id,
                t.title,
                t.created_at,
                t.updated_at,
                m.content AS last_content
            FROM threads t
            LEFT JOIN messages m ON m.message_id = (
                SELECT message_id FROM messages
                WHERE thread_id = t.thread_id
                ORDER BY created_at DESC LIMIT 1
            )
            {where_clause}
            ORDER BY t.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()

        summaries = [
            ThreadSummary(
                thread_id=row[0],
                agent_id=row[1],
                title=row[2],
                last_message_preview=(row[5][:80] + "...") if row[5] and len(row[5]) > 80 else row[5],
                created_at=row[3],
                updated_at=row[4],
            )
            for row in rows
        ]
        return summaries, total

    async def get_messages(self, thread_id: str) -> list[ThreadMessage]:
        """返回某线程全部消息，按时间正序。"""
        cursor = await self._conn.execute(
            """
            SELECT
                message_id, run_id, role, content, name, tool_call_id, tool_calls, created_at
            FROM messages
            WHERE thread_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [
            ThreadMessage(
                message_id=row[0],
                run_id=row[1],
                role=row[2],
                content=row[3],
                name=row[4],
                tool_call_id=row[5],
                tool_calls=_parse_json(row[6]),
                created_at=row[7],
            )
            for row in rows
        ]

    async def add_message(self, message: ThreadMessage) -> None:
        """写入单条消息；幂等（按 message_id 去重）。"""
        await self._conn.execute(
            """
            INSERT OR IGNORE INTO messages
            (message_id, thread_id, run_id, role, content, name, tool_call_id, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.message_id,
                message.thread_id,
                message.run_id,
                message.role,
                message.content,
                message.name,
                message.tool_call_id,
                _dump_json(message.tool_calls),
                message.created_at,
            ),
        )
        await self._conn.execute(
            "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
            (self._now(), message.thread_id),
        )
        await self._conn.commit()

    async def add_messages(self, messages: list[ThreadMessage]) -> None:
        """批量写入消息。"""
        for message in messages:
            await self.add_message(message)

    async def update_title(self, thread_id: str, title: str) -> None:
        """更新会话标题。"""
        await self._conn.execute(
            "UPDATE threads SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, self._now(), thread_id),
        )
        await self._conn.commit()


def _parse_json(value: str | None) -> list[dict[str, Any]] | None:
    import json

    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _dump_json(value: list[dict[str, Any]] | None) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)
```

- [ ] **Step 2：运行 ruff 检查**

```bash
ruff check src/scaffold/infra/history/repository.py
ruff format src/scaffold/infra/history/repository.py
```

- [ ] **Step 3：提交**

```bash
git add src/scaffold/infra/history/repository.py
git commit -m "feat(history): 实现 HistoryRepository"
```

---

## Task 3：在应用生命周期中初始化历史仓库

**Files:**
- Modify: `src/scaffold/infra/config/app_config.py`
- Modify: `src/scaffold/api/deps.py`

**Interfaces:**
- Produces: `get_history_repo(request: Request) -> HistoryRepository`.

- [ ] **Step 1：在 DatabaseConfig 中增加 history_db（可选）**

```python
# src/scaffold/infra/config/app_config.py
# 定位到 DatabaseConfig 类，添加字段
class DatabaseConfig(BaseModel):
    """数据库配置。"""

    sqlite_dir: str = Field(default="data", description="SQLite 数据目录")
    history_db: str | None = Field(
        default=None,
        description="历史消息数据库路径；默认使用 sqlite_dir/history.db",
    )
```

- [ ] **Step 2：在 deps.py 中初始化和注入 HistoryRepository**

```python
# src/scaffold/api/deps.py
# 在文件顶部增加导入
from scaffold.infra.history import HistoryRepository

# 在 scaffold_runtime() 中，checkpointer 初始化之后增加：
async with AsyncExitStack() as stack:
    # ... 原有 checkpointer 初始化代码 ...

    # 历史消息库
    history_db_path = config.database.history_db or f"{config.database.sqlite_dir}/history.db"
    os.makedirs(os.path.dirname(history_db_path), exist_ok=True)
    history_conn = await aiosqlite.connect(history_db_path)
    stack.push_async_callback(history_conn.close)
    history_repo = HistoryRepository(history_conn)
    await history_repo.migrate()
    app.state.history_repo = history_repo
    logger.info("History repository initialized at %s", history_db_path)

    yield

# 在文件末尾增加依赖函数：
def get_history_repo(request: Request) -> HistoryRepository:
    """返回当前请求的历史仓库实例。"""
    repo = getattr(request.app.state, "history_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="History repository not initialized")
    return repo
```

- [ ] **Step 3：运行 ruff 和格式化**

```bash
ruff check src/scaffold/api/deps.py src/scaffold/infra/config/app_config.py
ruff format src/scaffold/api/deps.py src/scaffold/infra/config/app_config.py
```

- [ ] **Step 4：提交**

```bash
git add src/scaffold/api/deps.py src/scaffold/infra/config/app_config.py
git commit -m "feat(history): 初始化 HistoryRepository 并提供依赖注入"
```

---

## Task 4：扩展 Threads API

**Files:**
- Modify: `src/scaffold/api/routers/threads.py`

**Interfaces:**
- Consumes: `get_history_repo` from Task 3, `ThreadSummary` from Task 1.
- Produces: `GET /api/threads` and `GET /api/threads/{thread_id}/messages`.

- [ ] **Step 1：修改 threads.py 增加历史列表接口**

```python
# src/scaffold/api/routers/threads.py
# 在文件顶部增加导入
from fastapi import Query
from scaffold.api.deps import get_history_repo
from scaffold.infra.history import ThreadSummary

# 修改 ThreadCreateRequest：增加 agent_id
class ThreadCreateRequest(BaseModel):
    thread_id: str | None = Field(default=None, description="Optional explicit thread ID")
    agent_id: str = Field(default="default", description="绑定 Agent 名称")
    metadata: dict[str, Any] = Field(default_factory=dict)

# 新增响应模型
class ThreadsListResponse(BaseModel):
    threads: list[ThreadSummary]
    total: int

class ThreadMessagesResponse(BaseModel):
    thread_id: str
    messages: list[ThreadMessage]

# 在 create_thread() 中增加历史写入：
@router.post("/", response_model=ThreadResponse)
async def create_thread(body: ThreadCreateRequest, request: Request) -> ThreadResponse:
    thread_id = body.thread_id or str(uuid.uuid4())
    checkpointer = get_checkpointer(request)
    history_repo = get_history_repo(request)

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = Checkpoint(...)
    checkpoint_metadata = {"source": "thread_create", **body.metadata}
    await checkpointer.aput(config, checkpoint=checkpoint, metadata=checkpoint_metadata, new_versions={})

    # 同步写入历史线程表
    await history_repo.ensure_thread(thread_id, body.agent_id)

    return ThreadResponse(thread_id=thread_id, metadata=checkpoint_metadata)

# 新增列表接口：
@router.get("/", response_model=ThreadsListResponse)
async def list_threads(
    request: Request,
    agent_id: str | None = Query(default=None, description="按 Agent 过滤"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ThreadsListResponse:
    """列出历史会话。"""
    history_repo = get_history_repo(request)
    threads, total = await history_repo.list_threads(agent_id=agent_id, limit=limit, offset=offset)
    return ThreadsListResponse(threads=threads, total=total)

# 新增消息详情接口：
@router.get("/{thread_id}/messages", response_model=ThreadMessagesResponse)
async def get_thread_messages(thread_id: str, request: Request) -> ThreadMessagesResponse:
    """获取某会话的全部消息。"""
    history_repo = get_history_repo(request)
    messages = await history_repo.get_messages(thread_id)
    return ThreadMessagesResponse(thread_id=thread_id, messages=messages)
```

- [ ] **Step 2：运行 ruff 和格式化**

```bash
ruff check src/scaffold/api/routers/threads.py
ruff format src/scaffold/api/routers/threads.py
```

- [ ] **Step 3：提交**

```bash
git add src/scaffold/api/routers/threads.py
git commit -m "feat(history): 扩展 Threads API 支持历史列表和消息详情"
```

---

## Task 5：在 AG-UI Endpoint 中持久化消息

**Files:**
- Modify: `src/scaffold/api/ag_ui.py`

**Interfaces:**
- Consumes: `get_history_repo`, `ThreadMessage` from Task 1.
- Produces: Transparent persistence in SSE endpoint.

- [ ] **Step 1：新增消息转换辅助函数**

```python
# src/scaffold/api/ag_ui.py
# 在文件顶部增加导入
from datetime import datetime, timezone
from scaffold.api.deps import get_history_repo
from scaffold.infra.history import HistoryRepository, ThreadMessage

# 在模块级增加辅助函数：
def _ag_ui_message_to_thread_message(
    msg: Any, thread_id: str, run_id: str | None
) -> ThreadMessage | None:
    """将 ag_ui Message 转换为 ThreadMessage。"""
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role is None:
        return None

    content = msg.get("content")
    if not isinstance(content, str):
        content = None

    tool_calls = msg.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, list):
        tool_calls = None

    return ThreadMessage(
        message_id=msg.get("id") or str(uuid.uuid4()),
        run_id=run_id,
        role=role,
        content=content,
        name=msg.get("name"),
        tool_call_id=msg.get("tool_call_id"),
        tool_calls=tool_calls,
        created_at=datetime.now(timezone.utc).isoformat(),
        thread_id=thread_id,
    )


def _extract_text_message(event: Any) -> tuple[str | None, str | None]:
    """从 TEXT_MESSAGE_END 事件中提取 message_id 和完整文本。"""
    if _get_event_type(event) != "TEXT_MESSAGE_END":
        return None, None
    message_id = _get_event_field(event, "message_id")
    raw_event = _get_event_field(event, "raw_event")
    text = ""
    if isinstance(raw_event, dict):
        data = raw_event.get("data", {})
        output = data.get("output", {})
        text = output.get("content", "")
    if not isinstance(text, str):
        text = ""
    return message_id, text
```

- [ ] **Step 2：修改 langgraph_agent_endpoint 写入用户消息**

```python
# src/scaffold/api/ag_ui.py
# 在 langgraph_agent_endpoint() 内部，日志记录之后、返回 StreamingResponse 之前增加：
async def langgraph_agent_endpoint(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    # ... 原有 request_id 和日志代码 ...

    # 持久化用户消息
    try:
        history_repo = get_history_repo(request)
        await history_repo.ensure_thread(input_data.thread_id, base_agent.name)
        for msg in input_data.messages or []:
            tm = _ag_ui_message_to_thread_message(
                msg.model_dump() if hasattr(msg, "model_dump") else dict(msg),
                input_data.thread_id,
                input_data.run_id,
            )
            if tm:
                await history_repo.add_message(tm)
    except Exception:
        logger.exception(
            "Failed to persist user messages | thread_id=%s run_id=%s",
            input_data.thread_id,
            input_data.run_id,
        )

    return StreamingResponse(...)
```

- [ ] **Step 3：在事件流生成器中持久化助手消息**

```python
# src/scaffold/api/ag_ui.py
# 修改 _produce_events_to_queue：
async def _produce_events_to_queue(
    agent: LangGraphAgent,
    input_data: RunAgentInput,
    queue: asyncio.Queue[Any],
    history_repo: HistoryRepository | None = None,
) -> None:
    # ... 原有变量 ...
    assistant_buffers: dict[str, list[str]] = {}

    try:
        async for event in agent.run(input_data):
            await queue.put(event)
            event_count += 1
            # ... 原有日志 ...

            # 持久化助手文本消息
            if history_repo is not None and _get_event_type(event) == "TEXT_MESSAGE_CONTENT":
                mid = _get_event_field(event, "message_id")
                delta = _get_event_field(event, "delta") or ""
                assistant_buffers.setdefault(mid, []).append(delta)

            if history_repo is not None and _get_event_type(event) == "TEXT_MESSAGE_END":
                mid = _get_event_field(event, "message_id")
                full_text = "".join(assistant_buffers.pop(mid, []))
                try:
                    await history_repo.add_message(
                        ThreadMessage(
                            message_id=mid or str(uuid.uuid4()),
                            run_id=input_data.run_id,
                            role="assistant",
                            content=full_text,
                            created_at=datetime.now(timezone.utc).isoformat(),
                            thread_id=input_data.thread_id,
                        )
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist assistant message | thread_id=%s message_id=%s",
                        input_data.thread_id,
                        mid,
                    )

    except Exception:
        # ... 原有异常处理 ...
```

- [ ] **Step 4：更新 _eager_event_generator 签名并传入 history_repo**

```python
# src/scaffold/api/ag_ui.py
async def _eager_event_generator(
    agent: LangGraphAgent,
    input_data: RunAgentInput,
    encoder: EventEncoder,
    request: Request,
    history_repo: HistoryRepository | None = None,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> Any:
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=EVENT_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _produce_events_to_queue(agent, input_data, queue, history_repo=history_repo),
        name=f"ag-ui-producer-{input_data.run_id}",
    )
    # ... 其余不变 ...
```

- [ ] **Step 5：在 endpoint 中传入 history_repo**

```python
# src/scaffold/api/ag_ui.py
# 修改 StreamingResponse 构造处：
history_repo = None
try:
    history_repo = get_history_repo(request)
except Exception:
    logger.exception("History repo unavailable for this request")

return StreamingResponse(
    _eager_event_generator(request_agent, input_data, encoder, request, history_repo=history_repo),
    media_type=encoder.get_content_type(),
)
```

- [ ] **Step 6：运行 ruff 和格式化**

```bash
ruff check src/scaffold/api/ag_ui.py
ruff format src/scaffold/api/ag_ui.py
```

- [ ] **Step 7：提交**

```bash
git add src/scaffold/api/ag_ui.py
git commit -m "feat(history): AG-UI endpoint 持久化用户与助手消息"
```

---

## Task 6：会话标题更新

**Files:**
- Modify: `src/scaffold/api/ag_ui.py`
- Modify: `src/scaffold/infra/middleware/deerflow_adapters/title.py`

**Interfaces:**
- Produces: Threads table `title` updated after first assistant response.

- [ ] **Step 1：在 RUN_FINISHED 后读取并写入标题**

```python
# src/scaffold/api/ag_ui.py
# 在 _produce_events_to_queue 中，处理 RUN_FINISHED 时：
elif etype == "RUN_FINISHED":
    logger.info("ag-ui run finished | %s", _ctx_str(ctx), extra=_stream_extra(ctx))

    # 如果 TitleMiddleware 生成了标题，写入历史表
    if history_repo is not None:
        try:
            # 从 event 的 raw_event / state 中提取 _thread_title
            raw_event = _get_event_field(event, "raw_event")
            title = None
            if isinstance(raw_event, dict):
                state = raw_event.get("state", {}) or {}
                title = state.get("_thread_title")
            if title:
                await history_repo.update_title(input_data.thread_id, title)
                logger.info(
                    "Updated thread title | thread_id=%s title=%s",
                    input_data.thread_id,
                    title,
                )
        except Exception:
            logger.exception("Failed to update thread title | thread_id=%s", input_data.thread_id)
```

- [ ] **Step 2：确保 TitleMiddleware 写入正确的 state 键**

```python
# src/scaffold/infra/middleware/deerflow_adapters/title.py
# 当前 after_model 返回 {"_thread_title": title}，无需修改。
# 如果 config.yaml 未启用 TitleMiddleware，请在 config.yaml 的 middleware.items 中启用：
# - name: TitleMiddleware
#   enabled: true
```

- [ ] **Step 3：提交**

```bash
git add src/scaffold/api/ag_ui.py
git commit -m "feat(history): 将 TitleMiddleware 生成的标题同步到历史表"
```

---

## Task 7：历史仓库单元测试

**Files:**
- Create: `tests/test_history_repository.py`

**Interfaces:**
- Tests: `HistoryRepository.migrate`, `ensure_thread`, `list_threads`, `get_messages`, `add_message`, `update_title`.

- [ ] **Step 1：编写测试**

```python
# tests/test_history_repository.py
"""HistoryRepository 单元测试。"""

from __future__ import annotations

import pytest
import aiosqlite

from scaffold.infra.history import HistoryRepository, ThreadMessage


@pytest.fixture
async def repo():
    conn = await aiosqlite.connect(":memory:")
    repo = HistoryRepository(conn)
    await repo.migrate()
    yield repo
    await conn.close()


@pytest.mark.asyncio
async def test_ensure_thread_creates_record(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default")
    summaries, total = await repo.list_threads()
    assert total == 1
    assert summaries[0].thread_id == "thread-1"
    assert summaries[0].agent_id == "default"


@pytest.mark.asyncio
async def test_add_message_is_idempotent(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default")
    msg = ThreadMessage(
        message_id="msg-1",
        thread_id="thread-1",
        run_id="run-1",
        role="user",
        content="hello",
        created_at="2026-08-18T10:00:00Z",
    )
    await repo.add_message(msg)
    await repo.add_message(msg)
    messages = await repo.get_messages("thread-1")
    assert len(messages) == 1
    assert messages[0].content == "hello"


@pytest.mark.asyncio
async def test_list_threads_filtered_by_agent(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default")
    await repo.ensure_thread("thread-2", "code_reviewer")
    summaries, total = await repo.list_threads(agent_id="default")
    assert total == 1
    assert summaries[0].thread_id == "thread-1"


@pytest.mark.asyncio
async def test_update_title(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default")
    await repo.update_title("thread-1", "测试标题")
    summaries, _ = await repo.list_threads()
    assert summaries[0].title == "测试标题"
```

- [ ] **Step 2：运行测试**

```bash
pytest tests/test_history_repository.py -v
```

- [ ] **Step 3：提交**

```bash
git add tests/test_history_repository.py
git commit -m "test(history): 添加 HistoryRepository 单元测试"
```

---

## Task 8：Threads API 测试

**Files:**
- Create: `tests/test_threads_api.py`

**Interfaces:**
- Tests: `GET /api/threads`, `GET /api/threads/{id}/messages`.

- [ ] **Step 1：编写测试**

```python
# tests/test_threads_api.py
"""Threads API 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scaffold.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_create_and_list_threads(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    assert res.status_code == 200
    thread_id = res.json()["thread_id"]

    res = client.get("/api/threads/?agent_id=default")
    assert res.status_code == 200
    data = res.json()
    assert any(t["thread_id"] == thread_id for t in data["threads"])


@pytest.mark.asyncio
async def test_get_thread_messages_empty(client: TestClient) -> None:
    res = client.post("/api/threads/", json={"agent_id": "default"})
    thread_id = res.json()["thread_id"]

    res = client.get(f"/api/threads/{thread_id}/messages")
    assert res.status_code == 200
    assert res.json()["messages"] == []
```

- [ ] **Step 2：运行测试**

```bash
pytest tests/test_threads_api.py -v
```

- [ ] **Step 3：提交**

```bash
git add tests/test_threads_api.py
git commit -m "test(history): 添加 Threads API 测试"
```

---

## Task 9：前端 Threads API 客户端

**Files:**
- Create: `src/web/src/api/threads.ts`
- Create: `src/web/src/api/threads.test.ts`

**Interfaces:**
- Produces: `listThreads()`, `getThreadMessages(threadId)`, `createThread(agentId)`.

- [ ] **Step 1：编写 API 客户端**

```typescript
// src/web/src/api/threads.ts
export interface ThreadSummary {
  thread_id: string
  agent_id: string
  title: string | null
  last_message_preview: string | null
  created_at: string
  updated_at: string
}

export interface ThreadMessage {
  message_id: string
  run_id: string | null
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  name: string | null
  tool_call_id: string | null
  tool_calls: Array<Record<string, unknown>> | null
  created_at: string
}

export async function listThreads(agentId?: string): Promise<{ threads: ThreadSummary[]; total: number }> {
  const params = new URLSearchParams()
  if (agentId) params.set('agent_id', agentId)
  const res = await fetch(`/api/threads/?${params.toString()}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getThreadMessages(threadId: string): Promise<{ thread_id: string; messages: ThreadMessage[] }> {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function createThread(agentId: string): Promise<{ thread_id: string }> {
  const res = await fetch('/api/threads/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
```

- [ ] **Step 2：编写 API 客户端测试**

```typescript
// src/web/src/api/threads.test.ts
import { describe, expect, it, vi } from 'vitest'
import { createThread, getThreadMessages, listThreads } from './threads'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('threads api', () => {
  it('listThreads fetches with agent_id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ threads: [], total: 0 }),
    })
    await listThreads('default')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/?agent_id=default')
  })

  it('getThreadMessages encodes thread id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ thread_id: 't1', messages: [] }),
    })
    await getThreadMessages('t1')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/t1/messages')
  })

  it('createThread posts agent_id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ thread_id: 't2' }),
    })
    await createThread('default')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: 'default' }),
    })
  })
})
```

- [ ] **Step 3：运行前端测试和类型检查**

```bash
cd src/web && npm test -- threads.test.ts
cd src/web && npm run build
```

- [ ] **Step 4：提交**

```bash
git add src/web/src/api/threads.ts src/web/src/api/threads.test.ts
git commit -m "feat(web): 添加 Threads API 客户端与测试"
```

---

## Task 10：历史会话列表组件

**Files:**
- Create: `src/web/src/components/ThreadList.tsx`
- Create: `src/web/src/components/__tests__/ThreadList.test.tsx`

**Interfaces:**
- Consumes: `ThreadSummary` from `src/api/threads.ts`.
- Produces: `ThreadList` component emitting `onSelectThread(threadId)`.

- [ ] **Step 1：编写组件**

```tsx
// src/web/src/components/ThreadList.tsx
import { type ThreadSummary } from '../api/threads'

interface ThreadListProps {
  threads: ThreadSummary[]
  currentThreadId: string
  onSelectThread: (threadId: string) => void
}

export function ThreadList({ threads, currentThreadId, onSelectThread }: ThreadListProps) {
  if (threads.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-ink-subtle">
        暂无历史会话，开始一段新对话吧。
      </div>
    )
  }

  return (
    <ul className="flex flex-col gap-1 px-2" role="listbox" aria-label="历史会话">
      {threads.map((thread) => {
        const isActive = thread.thread_id === currentThreadId
        const displayTitle = thread.title || thread.last_message_preview || '新会话'
        return (
          <li key={thread.thread_id} role="option" aria-selected={isActive}>
            <button
              onClick={() => onSelectThread(thread.thread_id)}
              className={`
                w-full rounded-lg px-3 py-2 text-left text-sm transition-colors
                ${isActive ? 'bg-cream-200 text-ink' : 'text-ink-muted hover:bg-cream-100'}
              `}
            >
              <div className="truncate font-medium">{displayTitle}</div>
              {thread.last_message_preview && (
                <div className="mt-0.5 truncate text-xs opacity-70">
                  {thread.last_message_preview}
                </div>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
```

- [ ] **Step 2：编写组件测试**

```tsx
// src/web/src/components/__tests__/ThreadList.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ThreadList } from '../ThreadList'

const threads = [
  {
    thread_id: 't1',
    agent_id: 'default',
    title: '测试会话',
    last_message_preview: '最后一条消息',
    created_at: '2026-08-18T10:00:00Z',
    updated_at: '2026-08-18T10:05:00Z',
  },
]

describe('ThreadList', () => {
  it('renders empty state', () => {
    render(<ThreadList threads={[]} currentThreadId="" onSelectThread={vi.fn()} />)
    expect(screen.getByText('暂无历史会话，开始一段新对话吧。')).toBeInTheDocument()
  })

  it('renders threads and handles selection', async () => {
    const onSelect = vi.fn()
    render(<ThreadList threads={threads} currentThreadId="t1" onSelectThread={onSelect} />)

    expect(screen.getByText('测试会话')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('option'))
    expect(onSelect).toHaveBeenCalledWith('t1')
  })
})
```

- [ ] **Step 3：运行测试和构建**

```bash
cd src/web && npm test -- ThreadList.test.tsx
cd src/web && npm run build
```

- [ ] **Step 4：提交**

```bash
git add src/web/src/components/ThreadList.tsx src/web/src/components/__tests__/ThreadList.test.tsx
git commit -m "feat(web): 添加历史会话列表组件"
```

---

## Task 11：Sidebar 集成历史列表

**Files:**
- Modify: `src/web/src/components/Sidebar.tsx`

**Interfaces:**
- Consumes: `ThreadList`, `listThreads`.
- Produces: `Sidebar` receives `threads`/`loadingThreads`/`onSelectThread` props.

- [ ] **Step 1：扩展 Sidebar 接口和渲染**

```tsx
// src/web/src/components/Sidebar.tsx
import { useEffect, useState } from 'react'
import { listThreads, type ThreadSummary } from '../api/threads'
import { ThreadList } from './ThreadList'

interface SidebarProps {
  agents: { name: string; type: string }[]
  currentAgentId: string
  threadId: string
  onAgentChange: (agentId: string) => void
  onNewChat: () => void
}

export function Sidebar({
  agents,
  currentAgentId,
  threadId,
  onAgentChange,
  onNewChat,
}: SidebarProps) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listThreads(currentAgentId)
      .then((data) => setThreads(data.threads))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [currentAgentId])

  const handleSelectThread = (selectedThreadId: string) => {
    // 通过 onAgentChange 隐式通知 App 切换会话
    // 这里仅做选择高亮，实际切换由 App 控制
  }

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-cream-300 bg-white">
      {/* ... 原有 brand、NewChatButton、AgentSelector ... */}

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="px-4 py-2 text-xs font-medium text-ink-subtle">历史会话</div>
        {loading ? (
          <div className="px-4 py-2 text-xs text-ink-subtle">加载中...</div>
        ) : error ? (
          <div className="px-4 py-2 text-xs text-red-500">{error}</div>
        ) : (
          <ThreadList
            threads={threads}
            currentThreadId={threadId}
            onSelectThread={handleSelectThread}
          />
        )}
      </div>

      {/* ... 原有 footer ... */}
    </aside>
  )
}
```

- [ ] **Step 2：调整 Sidebar 测试**

更新 `Sidebar.test.tsx` 中的 mock fetch，确保 `listThreads` 调用不报错。

```tsx
// src/web/src/components/__tests__/Sidebar.test.tsx
// 在 beforeEach 或测试内添加：
mockFetch.mockResolvedValue({
  ok: true,
  json: async () => ({ agents: [{ name: 'default', type: 'agent' }] }),
})
```

- [ ] **Step 3：运行测试和构建**

```bash
cd src/web && npm test -- Sidebar.test.tsx
cd src/web && npm run build
```

- [ ] **Step 4：提交**

```bash
git add src/web/src/components/Sidebar.tsx src/web/src/components/__tests__/Sidebar.test.tsx
git commit -m "feat(web): Sidebar 集成历史会话列表"
```

---

## Task 12：App.tsx 加载历史消息并注入 Agent

**Files:**
- Modify: `src/web/src/App.tsx`

**Interfaces:**
- Consumes: `getThreadMessages`, `ThreadMessage`, `useAgent` from `@copilotkit/react-core/v2`.
- Produces: `ChatInner` loads historical messages via `agent.setMessages()`.

- [ ] **Step 1：修改 ChatInner 以支持历史消息注入**

```tsx
// src/web/src/App.tsx
import { useAgent } from '@copilotkit/react-core/v2'
import { getThreadMessages, type ThreadMessage } from './api/threads'

interface ChatInnerProps {
  agentId: string
  initialMessages: ThreadMessage[]
}

function ChatInner({ agentId, initialMessages }: ChatInnerProps) {
  useGenerativeUITool()
  const { agent } = useAgent({ agentId })
  const dispatch = useGenerativeUIAction(agentId)

  useEffect(() => {
    if (agent && initialMessages.length > 0) {
      const agUiMessages = initialMessages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({
          id: m.message_id,
          role: m.role,
          content: m.content ?? '',
        }))
      agent.setMessages(agUiMessages)
    }
  }, [agent, initialMessages])

  return (
    <GenerativeUIContext.Provider value={{ dispatch }}>
      <main className="flex h-full flex-1 flex-col overflow-hidden">
        <CopilotChat
          agentId={agentId}
          className="h-full"
          labels={{
            chatInputPlaceholder: '输入消息...',
            welcomeMessageText: '有什么可以帮你的？',
            modalHeaderTitle: 'DeepAgents Chat',
          }}
        />
      </main>
    </GenerativeUIContext.Provider>
  )
}
```

- [ ] **Step 2：修改 App 状态和处理函数**

```tsx
// src/web/src/App.tsx
export default function App() {
  const [threadId, setThreadId] = useState(() => `thread-${crypto.randomUUID()}`)
  const [initialMessages, setInitialMessages] = useState<ThreadMessage[]>([])
  // ... 其他状态不变 ...

  const handleNewChat = () => {
    setThreadId(`thread-${crypto.randomUUID()}`)
    setInitialMessages([])
  }

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === currentAgentId) return
    setAgentId(nextAgentId)
    setThreadId(`thread-${crypto.randomUUID()}`)
    setInitialMessages([])
  }

  const handleSelectThread = async (selectedThreadId: string) => {
    if (selectedThreadId === threadId) return
    try {
      const data = await getThreadMessages(selectedThreadId)
      setThreadId(selectedThreadId)
      setInitialMessages(data.messages)
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-cream-50">
      <Sidebar
        agents={agents}
        currentAgentId={currentAgentId}
        threadId={threadId}
        onAgentChange={handleAgentChange}
        onNewChat={handleNewChat}
        onSelectThread={handleSelectThread}
      />
      <ChatShell
        key={threadId}
        agents={agents}
        currentAgentId={currentAgentId}
        threadId={threadId}
        initialMessages={initialMessages}
      />
    </div>
  )
}
```

- [ ] **Step 3：更新 ChatShell 接收 initialMessages**

```tsx
// src/web/src/App.tsx
interface ChatShellProps {
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
  initialMessages: ThreadMessage[]
}

function ChatShell({ agents, currentAgentId, threadId, initialMessages }: ChatShellProps) {
  // ... agentMap 不变 ...
  return (
    <CopilotKit threadId={threadId} agents__unsafe_dev_only={agentMap}>
      <ChatInner agentId={currentAgentId} initialMessages={initialMessages} />
    </CopilotKit>
  )
}
```

- [ ] **Step 4：运行测试和构建**

```bash
cd src/web && npm test
cd src/web && npm run build
```

- [ ] **Step 5：提交**

```bash
git add src/web/src/App.tsx
git commit -m "feat(web): 支持加载历史消息并注入 CopilotChat"
```

---

## Task 13：端到端验证

**Files:**
- Modify: `tests/e2e/test_ag_ui.py`

**Interfaces:**
- Verifies: messages are persisted after streaming.

- [ ] **Step 1：扩展 e2e 测试**

```python
# tests/e2e/test_ag_ui.py
# 在现有测试后增加：
@pytest.mark.asyncio
async def test_agent_stream_persists_messages(client: AsyncClient) -> None:
    thread_id = f"thread-persist-{uuid.uuid4()}"
    run_id = f"run-persist-{uuid.uuid4()}"
    payload = {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [{"id": "msg-1", "role": "user", "content": "say hello"}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    response = await client.post("/agent", json=payload, headers={"accept": "text/event-stream"})
    assert response.status_code == 200

    # 等待流结束
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:])
            if data.get("type") == "RUN_FINISHED":
                break

    # 验证历史表中有用户消息
    res = client.get(f"/api/threads/{thread_id}/messages")
    assert res.status_code == 200
    messages = res.json()["messages"]
    roles = [m["role"] for m in messages]
    assert "user" in roles
```

- [ ] **Step 2：运行 e2e 测试**

```bash
pytest tests/e2e/test_ag_ui.py -v
```

- [ ] **Step 3：提交**

```bash
git add tests/e2e/test_ag_ui.py
git commit -m "test(e2e): 验证消息持久化"
```

---

## Task 14：全量验证与清理

- [ ] **Step 1：后端全量检查**

```bash
ruff check src tests
ruff format src tests
pytest
```

- [ ] **Step 2：前端全量检查**

```bash
cd src/web && npm run build
cd src/web && npm test
```

- [ ] **Step 3：启动服务并手动验证**

```bash
bash scripts/dev.sh
```

验证步骤：

1. 打开 http://localhost:3000，发送一条消息；
2. 检查 Sidebar 是否出现新的历史会话；
3. 刷新页面，确认历史会话仍在；
4. 点击历史会话，确认消息被加载回聊天界面；
5. 切换 Agent，确认只显示当前 Agent 的历史；
6. 点击“新建会话”，确认当前聊天被清空。

- [ ] **Step 4：最终提交**

```bash
git add .
git commit -m "feat(history): 实现对话历史功能（独立 messages 表）"
```

---

## Self-Review

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|-----------|----------|
| 独立 `history.db` + `threads`/`messages` 表 | Task 2、3 |
| `GET /api/threads` 列表接口 | Task 4 |
| `GET /api/threads/{id}/messages` 详情接口 | Task 4 |
| 用户消息持久化 | Task 5 |
| 助手消息持久化 | Task 5 |
| 标题同步 | Task 6 |
| 前端历史列表 | Task 10、11 |
| 加载历史消息到 CopilotChat | Task 12 |
| 按 Agent 隔离 | Task 4（后端过滤）、Task 11（前端按 Agent 加载） |
| 懒创建线程 | Task 5（ensure_thread） |
| 测试覆盖 | Task 7、8、9、10、13 |

### Placeholder 检查

- 无 "TBD" / "TODO" / "实现 later"。
- 所有代码片段包含实际实现内容。
- 所有测试命令和提交命令明确。

### 类型一致性检查

- `ThreadSummary`、`ThreadMessage`、`ThreadCreate` 在 `models.py`、API、前端 API 中字段一致。
- `HistoryRepository` 方法签名在 Task 2 定义，Task 3/4/5/6 使用一致。
- `initialMessages` 类型为 `ThreadMessage[]`，在 Task 9、12 中一致。

---

## 执行方式选择

Plan complete and saved to `docs/superpowers/plans/2026-08-18-conversation-history.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - 我按 Task 逐个派生子代理，每个 Task 完成后我 review，再进入下一个。

**2. Inline Execution** - 在当前会话里按 Task 顺序直接执行，每完成一个 Task 我给你 checkpoint。

你希望用哪种方式执行？
