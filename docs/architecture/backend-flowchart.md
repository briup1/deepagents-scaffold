# DeepAgents Scaffold 后端流程图

本图梳理项目后端从启动、HTTP 请求处理、Agent 工厂编译到流式运行时输出的完整流程。

## 1. 总体流程图

```mermaid
flowchart TB
    subgraph 启动阶段
        A[app.py<br/>create_app] --> B[lifespan]
        B --> C[configure_proxy_environment]
        B --> D[get_app_config<br/>热重载加载 config.yaml]
        B --> E[configure_logging]
        B --> F[scaffold_runtime<br/>deps.py]
        F --> G[aiosqlite<br/>./data/checkpoints.db]
        F --> H[AsyncSqliteSaver]
        F --> I[make_stream_bridge<br/>MemoryStreamBridge]
        H --> J[app.state.checkpointer]
        I --> K[app.state.stream_bridge]
    end

    subgraph HTTP 网关层
        L[HTTP 请求] --> M[CORSMiddleware]
        M --> N[AuthMiddleware<br/>X-API-Key]
        N --> O[RequestIdMiddleware]
        O --> P[RateLimitMiddleware]
        P --> Q[LoggingMiddleware]
        Q --> R[ErrorHandlerMiddleware]
        R --> S[Router]
    end

    subgraph 路由层
        S --> T1["/health"]
        S --> T2["/api/agents"]
        S --> T3["/api/tools"]
        S --> T4["/api/threads"]
        S --> T5["/api/runs/stream<br/>POST"]
        S --> T6["/api/runs/wait<br/>POST"]
    end

    subgraph Agent 工厂 runtime/agents.py
        U[get_agent / create_agent] --> V[resolve ModelConfig]
        V --> W[create_chat_model<br/>infra/models/factory.py]
        U --> X[get_available_tools<br/>core/tools.py]
        X --> Y[load_tool_from_config]
        U --> Z[_build_system_prompt<br/>infra/prompts/assembler.py]
        U --> AA[build_middleware_chain<br/>infra/middleware/factory.py]
        U --> AB[_build_backend]
        U --> AC[_build_subagents<br/>core/subagents.py]
        U --> AD[_build_skills<br/>core/skills.py]
        U --> AE[_build_memory_sources]
        U --> AF[deepagents.create_deep_agent]
        AF --> AG[_agent_registry<br/>CompiledStateGraph]
    end

    subgraph 运行时速流 runtime/
        AH[_build_run_config] --> AI[run_worker<br/>runtime/worker.py]
        AI --> AJ[metadata pending]
        AJ --> AK[metadata running]
        AK --> AL[agent.astream]
        AL --> AM[_serialize_chunk]
        AM --> AN[StreamBridge.publish<br/>run_id]
        AN --> AO[MemoryStreamBridge<br/>_RunStream]
        AO --> AP[sse_consumer<br/>api/routers/runs.py]
        AP --> AQ[SSE 客户端]
        AI --> AR[metadata success/error]
        AR --> AS[END_SENTINEL]
        AS --> AT[cleanup delay 60s]
    end

    subgraph 插件系统
        AU[config.yaml tools] --> AV[plugins/tools/code_review.py]
        AW[config.yaml skills.path] --> AX[_scan_skill_directories]
        AX --> AY[SKILL.md 解析]
    end

    subgraph 配置与热重载 infra/config/
        AZ[config.yaml] --> BA[AppConfig.from_file]
        BA --> BB[递归解析 $ENV_VAR]
        BA --> BC[get_app_config 单例]
        BC --> BD[mtime 检测热重载]
    end

    subgraph 记忆与通道 infra/
        BE[MemoryStorage] --> BF[FileMemoryStorage]
        BG[MemoryUpdater] --> BH[extract_facts / merge_facts]
        BI[Channel ABC] --> BJ[SlackChannel]
        BI --> BK[FeishuChannel]
        BI --> BL[ChannelRouter]
    end

    S --> U
    T5 --> AH
    T6 --> AH
    D --> AZ
    AD --> AW
    X --> AU
```

## 2. 端到端请求流程

1. **启动**：`app.py:create_app` 组装 FastAPI，lifespan 里加载 `config.yaml`、初始化日志、打开 SQLite checkpointer、创建 `MemoryStreamBridge`，全部挂到 `app.state`。
2. **HTTP 进入**：请求依次经过 CORS → Auth → RequestId → RateLimit → Logging → ErrorHandler。
3. **路由分发**：`/api/runs/stream` 或 `/api/runs/wait` 进入运行处理。
4. **Agent 解析**：`get_agent(assistant_id)` 命中注册表则复用，否则 `create_agent(...)` 按配置现场编译 LangGraph。
5. **构造运行配置**：生成 `thread_id`、`run_id`，注入 `recursion_limit`。
6. **后台 Worker**：`run_worker` 调用 `agent.astream`，把每个 chunk 序列化后发到 `StreamBridge`。
7. **消费端**：
   - `/stream`：`sse_consumer` 从桥读取并返回 SSE。
   - `/wait`：阻塞到 `END_SENTINEL` 后返回最终 checkpoint。
8. **清理**：运行结束后 60 秒触发 `bridge.cleanup(run_id)`。

## 3. 关键文件速查

| 职责 | 文件 |
|------|------|
| FastAPI 入口 | `src/scaffold/api/app.py` |
| 运行时依赖/单例 | `src/scaffold/api/deps.py` |
| Agent 工厂 | `src/scaffold/runtime/agents.py` |
| 工具加载 | `src/scaffold/core/tools.py` |
| 子 Agent | `src/scaffold/core/subagents.py` |
| Skill 扫描 | `src/scaffold/core/skills.py` |
| 模型工厂 | `src/scaffold/infra/models/factory.py` |
| 配置系统 | `src/scaffold/infra/config/app_config.py` |
| 中间件链 | `src/scaffold/infra/middleware/factory.py` |
| StreamBridge | `src/scaffold/runtime/stream_bridge/memory.py` |
| 后台 Worker | `src/scaffold/runtime/worker.py` |
| 主配置 | `config.yaml` |
| 验证配置 | `config.verify.yaml` |
