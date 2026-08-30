# DeepAgents Scaffold

基于 **DeepAgents SDK**（LangChain/LangGraph）构建、基础设施移植自 **Deer-Flow** 的生产级多 Agent 项目脚手架。

使用本模板可快速开发具备可配置中间件、通道、记忆和链路追踪的生产级多 Agent 应用。

## 特性

- **DeepAgents SDK** — 以官方 LangChain 多 Agent 框架作为核心运行时，完整集成中间件
- **Deer-Flow 基础设施** — YAML 配置（热重载）、模型工厂、结构化日志、IM 通道
- **中间件框架** — 可插拔 AgentMiddleware 链：循环检测、Token 追踪、动态上下文、工具错误处理
- **FastAPI 网关** — 具备认证、限流、请求追踪、CORS、静态文件的 REST API
- **提示词工程** — 基于模板的系统提示词组装（USER -&gt; BASE -&gt; CUSTOM -&gt; SUFFIX）
- **通道适配器** — Slack、飞书、Telegram 集成框架
- **记忆系统** — DeepAgents MemoryMiddleware 配合持久化存储
- **技能系统** — SKILL.md 发现与加载
- **SQLite 检查点器** — 开箱即用的会话持久化
- **极简 Web UI** — React + Vite 聊天界面，支持 Agent 切换

## 快速开始

```bash
# 1. 克隆并进入项目
git clone <本仓库地址> my-agent-project
cd my-agent-project

# 2. 创建虚拟环境并安装依赖
uv venv
uv pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 并填入你的 API 密钥

# 4. 同时启动后端与前端
chmod +x scripts/dev.sh
./scripts/dev.sh
```

打开：

- **前端**：[http://localhost:3002](http://localhost:3002)
- **API 文档**：[http://localhost:8000/docs](http://localhost:8000/docs)
- **健康检查**：[http://localhost:8000/health](http://localhost:8000/health)

## 项目结构

```
.
├── config.yaml              # 主配置（模型、工具、记忆、通道、中间件、profile）
├── src/
│   ├── scaffold/
│   │   ├── core/            # DeepAgents 集成
│   │   │   ├── agents.py    # Agent 工厂，完整注入中间件/profile/后端
│   │   │   ├── tools.py     # 工具注册与发现
│   │   │   └── skills.py    # SKILL.md 加载
│   │   ├── infra/           # Deer-Flow 基础设施
│   │   │   ├── config/      # YAML 配置系统，支持热重载
│   │   │   ├── middleware/  # 中间件注册表 + Deer-Flow 适配器
│   │   │   ├── models/      # 多模型工厂
│   │   │   ├── logging/     # 结构化 JSON 日志
│   │   │   ├── prompts/     # 提示词模板注册表与组装器
│   │   │   └── channels/    # IM 平台适配器框架
│   │   ├── api/             # FastAPI 网关
│   │   │   ├── app.py
│   │   │   ├── middleware/  # 认证、限流、请求 ID、错误处理
│   │   │   └── routers/
│   │   └── plugins/         # 你的扩展放在这里
│   │       ├── tools/       # 自定义工具模块
│   │       └── skills/      # SKILL.md 定义
│   └── web/                 # React 前端
│       ├── src/
│       ├── static/
│       └── package.json
├── tests/                   # pytest 测试集
└── scripts/dev.sh           # 一键启动开发环境
```

## 配置

编辑 `config.yaml` 以设置你的项目：

```yaml
models:
  - name: openai-gpt-4o
    use: langchain_openai:ChatOpenAI
    api_key: $OPENAI_API_KEY
    model: gpt-4o
    supports_vision: true

tools:
  - name: my_tool
    use: scaffold.plugins.tools.my_tool:my_async_function

middleware:
  items:
    - name: LoopDetectionMiddleware
      enabled: true
    - name: TokenUsageMiddleware
      enabled: true

profiles:
  harness:
    - name: coding
      base_system_prompt: "You are an expert software engineer..."
```

**热重载**：`config.yaml` 的修改在下一次 API 请求时自动生效，无需重启服务。

## 部署前置

- **多用户认证**：`config.yaml` 的 `auth` 段配置 token → user_id 映射（token 用 `$ENV_VAR` 引用，缺失时启动失败）。`enabled: false` 时全放行（仅限本地开发）。
- **代码执行沙箱**：默认 `execution_sandbox.provider: bwrap`（bubblewrap 本地隔离）。Ubuntu 23.10+ 需先执行一次 `sudo bash scripts/setup_bwrap_apparmor.sh` 放行 unprivileged userns（幂等）。无 bwrap 的环境可退回 `provider: subprocess`（仅 AST 扫描，无系统级隔离）。

## 中间件

本脚手架支持 DeepAgents `AgentMiddleware` 与 Deer-Flow 适配器中间件：


| 中间件                           | 来源         | 用途               |
| ----------------------------- | ---------- | ---------------- |
| `MemoryMiddleware`            | DeepAgents | 将记忆上下文注入系统提示词    |
| `SkillsMiddleware`            | DeepAgents | 加载并注入技能指令        |
| `SubAgentMiddleware`          | DeepAgents | 启用子 Agent 委派     |
| `FilesystemMiddleware`        | DeepAgents | 文件操作工具           |
| `LoopDetectionMiddleware`     | Deer-Flow  | 检测并中断重复性工具调用循环   |
| `ToolErrorHandlingMiddleware` | Deer-Flow  | 捕获工具异常并转换为错误消息   |
| `DynamicContextMiddleware`    | Deer-Flow  | 将日期/时间与记忆注入上下文   |
| `TokenUsageMiddleware`        | Deer-Flow  | 逐轮追踪并记录 Token 消耗 |
| `SafetyTerminationMiddleware` | Deer-Flow  | 检测提供商的安全拒绝信号     |
| `TodoMiddleware`              | Deer-Flow  | 管理待办列表并检测上下文丢失   |
| `TitleMiddleware`             | Deer-Flow  | 自动生成会话标题         |


在 `config.yaml` 中声明中间件：

```yaml
middleware:
  items:
    - name: LoopDetectionMiddleware
      enabled: true
      kwargs:
        warn_threshold: 3
        hard_stop_threshold: 5
```

## 添加自定义中间件

创建一个继承自 `AgentMiddleware` 的类：

```python
from langchain.agents.middleware.types import AgentMiddleware

class MyMiddleware(AgentMiddleware):
    def before_model(self, state, runtime):
        # 在 LLM 调用前修改状态
        return {"messages": state["messages"] + [SystemMessage(content="提醒")]}
```

在 `config.yaml` 中通过完整导入路径注册：

```yaml
middleware:
  items:
    - name: mypackage.mymodule:MyMiddleware
      enabled: true
```

## 添加自定义工具

在 `src/scaffold/plugins/tools/` 中创建模块：

```python
# src/scaffold/plugins/tools/my_tool.py
async def search_database(query: str) -> str:
    """搜索内部数据库。"""
    return f"Results for: {query}"
```

然后在 `config.yaml` 中注册：

```yaml
tools:
  - name: search_database
    use: scaffold.plugins.tools.my_tool:search_database
```

## 添加自定义 Agent

```python
from scaffold.core.agents import create_agent

agent = create_agent(
    name="researcher",
    model_name="openai-gpt-4o",
    system_prompt="你是一个研究助手...",
)
```

## API 端点


| 方法   | 路径                        | 说明           |
| ---- | ------------------------- | ------------ |
| GET  | `/health`                 | 健康检查         |
| GET  | `/api/agents/`            | 列出已注册的 agent |
| GET  | `/api/tools/`             | 列出可用工具       |
| POST | `/api/threads/`           | 创建对话线程       |
| GET  | `/api/threads/{id}`       | 获取线程信息       |
| GET  | `/api/threads/{id}/state` | 获取线程状态       |
| POST | `/api/threads/{id}/state` | 更新线程状态       |
| POST | `/api/runs/stream`        | 流式响应（SSE）    |
| POST | `/api/runs/wait`          | 阻塞等待响应       |


## IM 通道集成

在 `config.yaml` 中启用通道：

```yaml
channels:
  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN
    app_token: $SLACK_APP_TOKEN
```

安装通道依赖：

```bash
uv pip install -e ".[channels]"
```

## 链路追踪

在 `config.yaml` 中启用可观测性：

```yaml
tracing:
  enabled: true
  providers: ["langsmith", "langfuse"]
```

在 `.env` 中设置对应的环境变量。

## 开发

```bash
# 运行测试
pytest

# 格式化代码
ruff format src tests

# 检查
ruff check src tests
```

## 许可证

MIT