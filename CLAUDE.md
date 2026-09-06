# CLAUDE.md

本文件为 Claude Code 在本 monorepo 仓库中工作时的顶层指引地图。详细后端/前端指南分别见 `src/scaffold/CLAUDE.md` 与 `src/web/CLAUDE.md`。

## 0. AI 编码约束（宪法区，由 harness 体系维护）

> 本区由 `docs/harness/` 规范体系维护（生成：harness-bootstrap；变更追踪见 `docs/harness/changes/`）。
> 红线细则与各阶段流程见 `docs/harness/rules/`、`docs/harness/skills/`；本区为技术栈、红线、文件索引三部分。
> 红线标注：✅ 项目已遵守 | ⚠️ 现状违反（技术债）| ❓ 新提议。

### 0.1 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18.3 / TypeScript 5.6（strict）/ Vite 5.4 / Tailwind CSS 3.4 / CopilotKit v2（`@copilotkit/react-core`、`@ag-ui/client` HttpAgent） |
| 后端 | Python 3.12+ / FastAPI 0.115+ / DeepAgents SDK + LangGraph / Pydantic 2 / ag-ui-langgraph（SSE） |
| 存储 | SQLite（`data/`：业务表 + LangGraph checkpoint + 工件元数据），无 Redis / 消息队列 |
| 工具链 | ruff（line-length=120, py312）/ pytest + pytest-asyncio / Vitest + React Testing Library + jsdom / Playwright（e2e） |
| 配置 | `config.yaml` 唯一事实来源，支持 `$ENV_VAR` 替换与 mtime 热重载（`SCAFFOLD_CONFIG_PATH` 切换） |

### 0.2 红线（不可违反）

1. 所有 LLM 可调用工具必须是 `async` 函数并接受关键字参数 🔴（✅ `plugins/tools/` 全部工具模块遵守，`core/tools.py` 动态加载）
2. 分层依赖方向：`core → infra`、`api → infra`、`runtime → core + infra` 允许；`infra → core/api`、`core ↔ api` 禁止 🔴（✅ `tests/test_layering.py` AST 扫描强制）
3. 禁止硬编码 API Key / Token / 密钥；配置一律 `$ENV_VAR` 引用，敏感文件（`.env*`）禁止入库 🔴（✅ `config.yaml` 全量遵守）
4. 禁止在异常处理中忽略错误（`except: pass` 且不复记日志）🔴（⚠️ 债务：`infra/sandbox/bwrap_sandbox.py:163`、`subprocess_sandbox.py:196`）
5. Python 函数必须带完整类型注解，模块头统一 `from __future__ import annotations`；禁止裸 `dict` 传业务数据（用 Pydantic 模型）🔴（✅ 全仓惯例）
6. 前端 TypeScript 严格模式，未知结构用 `unknown` + 收窄，禁止 `any` 逃逸 🔴（⚠️ 债务：`src/web/src/catalog/createCatalog.tsx:144` 现存 1 处）
7. 前端所有 HTTP 请求必须走 `apiFetch`/`apiFetchJson` 统一封装（注入 `X-API-Key`、统一 401 处理），禁止散落裸 `fetch` 🔴（✅ `src/web/src/api/` 全部遵守）
8. 后端错误响应必须经 `ErrorHandlerMiddleware` 统一结构 `{detail, request_id, type}`；路由禁止吞异常返回裸 500 堆栈 🔴（✅；决策：不引入业务错误码体系）
9. 生产日志禁止打印敏感信息（API Key、Token、用户隐私数据）🔴（⚠️ 日志系统当前无脱敏机制，脱敏为 ❓ 新提议，见 `docs/harness/rules/编码规范.md`）
10. 单函数不超过 80 行，超过即考虑拆分 🔴（❓ 新提议，历史代码普遍合规）
11. AI 生成文档（设计稿、计划、README、注释）一律使用中文 🔴（✅ 本仓约定）

### 0.3 文件索引

| 文件 | 用途 |
|------|------|
| `docs/harness/agents/owner.md` | 应用 Owner Agent 定义 |
| `docs/harness/rules/工程结构.md` | 项目目录结构与分层规范 |
| `docs/harness/rules/编码规范.md` | 编码标准与约定 |
| `docs/harness/rules/开发流程规范.md` | 开发流水线与流程 |
| `docs/harness/skills/` | 需求分析 / 编码实现 / 代码审查 / 专家评审 / 单元测试编写 / 单元测试CI / 部署验证 |
| `docs/harness/wiki/业务模型.md` | 业务模型与领域划分 |
| `docs/harness/wiki/接口协议.md` | API 接口协议定义 |
| `docs/harness/wiki/数据模型.md` | 数据库 Schema |
| `docs/harness/wiki/领域术语.md` | 领域术语表（统一语言） |
| `docs/harness/changes/` | 变更追踪 |

---

## 1. 项目概述

基于 DeepAgents SDK + Deer-Flow 基础设施的生产级多 Agent 脚手架，聚合后端（FastAPI）与前端（React）的 monorepo。后端提供 Agent 工厂、可插拔中间件链、记忆、历史会话持久化与通道；前端基于 CopilotKit v2 提供 SSE 流式聊天界面与 Generative UI Catalog。仓库以 `config.yaml` 为唯一配置来源并支持热重载。

## 2. AI 协作原则

- 修改超过 6 个文件时，先拆分子任务并说明依赖关系
- 修 bug 前先写复现测试，修复后确保测试通过
- 需求模糊时先提问澄清，再动手实现
- 跨前后端改动时，先确认接口契约（URL、方法、请求/响应体）
- 改完必须给出可独立执行的验证命令，禁止只写“已验证”
- 所有 AI 生成的文档（设计稿、计划、README、注释等）一律使用中文

## 3. 快速命令

| 命令 | 说明 |
|------|------|
| `uv pip install -e ".[dev]"` 或 `uv sync` | 安装后端开发依赖 |
| `bash scripts/dev.sh` | 同时启动后端（8000）与前端（3002） |
| `bash scripts/stop_dev.sh` | 停止后端与前端开发服务 |
| `bash scripts/verify_dev.sh` | 使用 `config.verify.yaml` + mock 模型启动验证模式 |
| `pytest` | 运行全部后端测试 |
| `pytest tests/test_api.py::test_health_check -v` | 运行单个健康检查测试 |
| `ruff check src tests` | 后端代码检查 |
| `ruff format src tests` | 后端代码格式化 |
| `cd src/web && npm install` | 安装前端依赖（`dev.sh` 已自动执行） |
| `cd src/web && npm run dev` | 启动前端开发服务器 |
| `cd src/web && npm run build` | 前端生产构建 |
| `cd src/web && npm test` | 运行前端测试 |

### 环境变量

1. 复制模板：`cp .env.example .env`
2. 在 `.env` 中填入 API Key、通道 Token 等敏感信息
3. 启动脚本或 `python-dotenv` 会自动加载 `.env`
4. 可选：通过 `SCAFFOLD_CONFIG_PATH` 指定配置文件（默认 `config.yaml`）；`scripts/verify_dev.sh` 已设置为 `config.verify.yaml`
5. 可选：在 `config.yaml` 的 `auth.users` 配置 token→user 映射启用多用户认证（token 用 `$ENV_VAR` 引用环境变量，缺失时启动失败）；`auth.enabled: false` 时网关不开启认证（统一 `X-API-Key` 请求头）

## 4. 后端架构

```
src/scaffold/
├── api/           # FastAPI 路由与 HTTP 中间件
├── core/          # DeepAgents SDK 集成：Agent 工厂、工具、技能
├── infra/         # 基础设施：配置、模型、日志、通道、提示词、历史、中间件
├── plugins/       # 自定义工具与 SKILL.md
└── runtime/       # 运行时编排：Agent 工厂、注册表与通道路由
```

- 分层依赖方向：`core → infra`、`api → infra`、`runtime → core + infra` 允许；反向与 `core ↔ api` 禁止
- 自定义工具放 `plugins/tools/`，在 `config.yaml` 注册
- 自定义中间件继承 `AgentMiddleware`，在 `config.yaml` 注册
- `infra/history/` 提供基于 SQLite 的历史会话与消息持久化
- 详见 `src/scaffold/CLAUDE.md`

## 5. 前端架构

- **技术栈**：React 18.3 + TypeScript 5.6 + Vite 5.4 + Tailwind CSS 3.4 + CopilotKit v2
- **入口**：`src/web/src/main.tsx`，开发服务器端口 3002，`/api` 与 `/agent` 代理到 `localhost:8000`
- **API 客户端**：`src/web/src/api/copilotkit.ts`（Agent 列表）与 `src/web/src/api/threads.ts`（线程/历史消息）
- **聊天框架**：`@copilotkit/react-core/v2` 的 `CopilotKit` + `CopilotChat`，通过 `@ag-ui/client` 的 `HttpAgent` 直连后端 `/agent/{agentId}` SSE 端点
- **Generative UI**：`src/web/src/catalog/` 提供可扩展的组件目录（MarkdownCard、DataTable、Form、ButtonGroup、MetricCard、Chart），Agent 通过 `render_ui` 工具渲染组件
- 单 Agent 场景仍保留 `/agent` 别名保持兼容
- 详见 `src/web/CLAUDE.md`

## 6. 关键约定

- **配置驱动**：`config.yaml` 是唯一事实来源，支持热重载；开发/验证/测试分别使用 `config.yaml`、`config.verify.yaml`、`config.test.yaml`，通过 `SCAFFOLD_CONFIG_PATH` 切换
- **依赖管理**：新增或更新 Python 依赖时，始终通过 `uv add <package>` 安装，禁止直接编辑 `pyproject.toml` 或 `uv.lock`
- **工具必须异步**：所有 LLM 可调用工具必须是 `async` 并接受关键字参数
- **类型完整**：Python 函数必须带类型注解；TypeScript 使用严格模式
- **分层依赖**：禁止 `infra` 依赖 `core` 或 `api`，禁止 `core` 与 `api` 直接互调
- **命名**：Python 用 snake_case/PascalCase；前端组件用 PascalCase
- **代码风格**：Python 遵循 ruff（line-length=120, target-version=py312）

### 禁止事项

- 禁止硬编码 API Key、密码、密钥；统一使用 `.env` + 环境变量替换
- 禁止提交 `.env`、`.env.copy` 或任何含敏感值的文件到 Git
- 禁止在异常处理中忽略错误，尤其是中间件和工具函数
- 禁止在生产日志中打印敏感信息（API Key、Token、用户隐私数据）
- 禁止绕过 `ruff check` 提交代码

## 7. 本地开发及验证流程

改 → 检查 → 测试 → 启动 → 验证：

1. 修改代码
2. `ruff check src tests && ruff format src tests`
3. `pytest`
4. `cd src/web && npm run build`（前端构建/类型检查）
5. `cd src/web && npm test`（前端测试）
6. `bash scripts/dev.sh`
7. 独立验证：
   - 后端健康检查：`curl -s http://localhost:8000/health`
   - API 文档：`http://localhost:8000/docs`
   - 前端页面：`http://localhost:3002`
   - ag-ui 流式接口测试（默认 Agent 别名）：

     ```bash
     curl -N -X POST http://localhost:8000/agent \
       -H "Content-Type: application/json" \
       -H "Accept: text/event-stream" \
       -d '{"threadId":"thread-verify-001","runId":"run-verify-001","messages":[{"id":"msg-001","role":"user","content":"hello"}],"state":{},"tools":[],"context":[],"forwardedProps":{}}'
     ```

   - 多 Agent 场景使用 `/agent/{agentId}`，例如：

     ```bash
     curl -N -X POST http://localhost:8000/agent/coding \
       -H "Content-Type: application/json" \
       -H "Accept: text/event-stream" \
       -d '{"threadId":"thread-verify-001","runId":"run-verify-001","messages":[{"id":"msg-001","role":"user","content":"hello"}],"state":{},"tools":[],"context":[],"forwardedProps":{}}'
     ```

   - 验证模式：`bash scripts/verify_dev.sh`（无需真实模型 API Key，使用 `config.verify.yaml` 中的 mock 模型）

### 日志与排查

- 后端日志：`logs/` 目录
- 前端构建错误：`cd src/web && npm run build`
- 前端测试失败：`cd src/web && npm test`
- 测试失败：`pytest -v`
- 若启动时报配置错误，检查 `SCAFFOLD_CONFIG_PATH` 指向的文件是否存在且 YAML 合法
