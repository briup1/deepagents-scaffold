# CLAUDE.md

本文件为 Claude Code 在本 monorepo 仓库中工作时的顶层指引地图。详细后端/前端指南分别见 `src/scaffold/CLAUDE.md` 与 `src/web/CLAUDE.md`。

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
5. 可选：设置 `SCAFFOLD_API_KEY` 启用简单 API Key 认证；未设置时网关不开启认证

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
