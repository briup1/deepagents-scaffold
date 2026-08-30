# 后端项目指南

本文件聚焦 `src/scaffold/` 内的后端实现。AI 协作原则、安全红线、跨前后端验证闭环、环境变量配置见根目录 `CLAUDE.md`。

## 项目简介

基于 DeepAgents SDK 的多 Agent 后端服务。提供 FastAPI 网关、Agent 工厂、中间件链、记忆系统、通道适配和流式响应。

## 项目结构

```
src/scaffold/
├── api/           # 网关层：FastAPI 路由与 HTTP 中间件
├── core/          # 运行时层：DeepAgents SDK 集成
├── infra/         # 基础设施层：配置、模型、日志、通道、提示词
├── plugins/       # 扩展：自定义工具和 SKILL.md
└── runtime/       # 运行时编排：Agent 工厂、注册表与通道路由
```

## 常用命令

```bash
# 运行 FastAPI 服务（带热重载）
PYTHONPATH=src uvicorn scaffold.api.app:app --reload

# 运行全部测试
pytest

# 运行单个测试文件
pytest tests/test_config.py

# 运行指定测试
pytest tests/test_api.py::test_health -v

# 格式化与检查
ruff format src tests
ruff check src tests
```

## 分层模式

项目按四层组织，添加功能时请放入正确层级：

| 层级 | 路径 | 职责 |
|------|------|------|
| 运行时层 | `core/` | DeepAgents SDK 集成，Agent 工厂 |
| 网关层 | `api/` | FastAPI 路由、认证、限流 |
| 基础设施层 | `infra/` | 配置、模型、日志、通道（框架无关） |

## 模块引用规范

四层依赖方向必须遵守：

```
core → infra  ✓（允许）
api  → infra  ✓（允许）
infra → core  ✗（禁止）
infra → api   ✗（禁止）
core ↔ api    ✗（禁止直接调用）
```

## 核心模块说明

### runtime/agents.py — Agent 工厂

核心函数：
- `create_agent()`: 构建完整的 DeepAgents agent
- `get_agent()`: 获取已编译的 agent 实例
- `list_agents()`: 列出所有已注册 agent

构建流程：
1. 加载 AppConfig（热重载感知）
2. 解析模型配置 → create_chat_model()
3. 解析工具 → get_available_tools()
4. 构建系统提示词：用户覆盖 > harness profile > PromptAssembler 默认模板
5. 构建中间件链：config 中的 Deer-Flow 适配器 + DeepAgents 原生中间件
6. 构建子 Agent：从 config 的 subagent_definitions
7. 构建后端：filesystem/sandbox/composite
8. 调用 deepagents.create_deep_agent(...)

### infra/config/ — 配置系统

核心类：
- `AppConfig`: 根配置 + YAML 加载 + mtime 热重载
- `ModelConfig`: LLM 提供商配置
- `HarnessProfileConfig`: Agent 行为画像

配置驱动：
- `config.yaml` 是唯一事实来源
- 支持环境变量替换（`$ENV_VAR`）
- 支持热重载（基于文件 mtime）

### infra/middleware/ — 中间件系统

Agent 中间件（DeepAgents 层）：
- `LoopDetectionMiddleware`: 检测重复工具调用循环
- `ToolErrorHandlingMiddleware`: 工具异常捕获
- `DynamicContextMiddleware`: 注入日期/记忆上下文
- `TokenUsageMiddleware`: token 消耗追踪
- `SafetyTerminationMiddleware`: 安全拒绝信号检测
- `DeepAgentsSummarizationMiddleware`: 继承 DeepAgents 原生 SummarizationMiddleware，支持通过 `config.yaml` 自定义 trigger/keep/summary_prompt 等参数，上下文窗口满时生成摘要
- `TodoMiddleware`: 待办事项跟踪提醒
- `TitleMiddleware`: 自动生成会话标题

HTTP 中间件（API 层）：
- `AuthMiddleware`: API Key 认证
- `ErrorHandlerMiddleware`: 全局异常捕获
- `RateLimitMiddleware`: 基于 IP 的内存限流器
- `RequestIdMiddleware`: 请求 ID 注入/透传

### infra/prompts/ — 提示词工程系统

核心类：
- `PromptAssembler`: USER → BASE → CUSTOM → SUFFIX 组装
- `PromptLoader`: 从磁盘加载 .md 模板
- `PromptRegistry`: 具名模板注册表

组装顺序：
1. USER: 调用者提供的指令（前置）
2. BASE: 默认行为（从 templates/base.md 加载）
3. CUSTOM: 如果提供，替换 BASE
4. SUFFIX: 最后追加，用于模型调优

### core/tools.py — 工具系统

工具注册与发现：
- 从 config.yaml 动态加载工具
- 支持完整导入路径（`mymodule:my_function`）
- 工具必须是异步的，并接受关键字参数

### core/skills.py — 技能系统

技能发现：
- 扫描 SKILL.md 文件
- 解析 frontmatter 元数据
- 支持热重载

## 测试约定

- 使用 `TestClient` 作为上下文管理器（lifespan 依赖）
- 测试文件命名：`test_*.py`
- 测试函数命名：`test_*`
- fixture 定义在 `tests/conftest.py`

## 添加自定义工具

在 `plugins/tools/` 中创建异步可调用对象，然后在 `config.yaml` 中注册：

```yaml
tools:
  - name: my_tool
    use: scaffold.plugins.tools.my_module:my_async_function
```

函数必须是异步的，并接受与你想让 LLM 看到的 schema 匹配的关键字参数。

## 添加自定义中间件

创建一个 `AgentMiddleware` 子类。可以放在任何可导入位置。在 `config.yaml` 中通过别名注册（如果已加入 `MiddlewareRegistry`）或完整导入路径注册：

```yaml
middleware:
  items:
    - name: mypackage.mymodule:MyMiddleware
      enabled: true
      kwargs:
        threshold: 5
```

## 网关中间件堆叠顺序

在 `api/app.py` 中，中间件按「外层最后添加」的顺序注册。实际包裹顺序为：

1. CORS（最外层）
2. AuthMiddleware
3. RequestIdMiddleware
4. RateLimitMiddleware
5. LoggingMiddleware
6. ErrorHandlerMiddleware（最内层 —— 捕获所有异常）

## 关键数据流

请求生命周期：
1. HTTP 请求到达 `api/app.py`
2. 中间件链依次处理
3. 路由匹配到 ag-ui `/agent` 端点
4. handler 解析 ag-ui 请求体并提取 `threadId`、`runId`、`messages` 等参数
5. handler 通过 `deps.py` 获取 `checkpointer`
6. `runtime/agents.py:create_agent()` 构建 DeepAgents agent
7. ag-ui-langgraph 将 graph 包装为 LangGraphAgent 并暴露 `/agent` SSE 端点

## 日志与调试

- 结构化 JSON 日志配置在 `infra/logging/`
- 运行日志写入项目根目录 `logs/`
- 配置变更无需重启服务（热重载）
- 工具和中间件支持动态加载
- 记忆系统支持跨会话持久化
