# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库中工作时提供指引。

## 常用命令

```bash
# 安装依赖
uv pip install -e ".[dev]"

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

# 同时启动后端与前端
bash scripts/dev.sh
```

## 架构

### 三层设计

项目按三层组织。添加功能时，请放入正确的层级：

1. **运行时层（`src/scaffold/core/`）** — 直接与 DeepAgents SDK 集成。`agents.py` 是核心工厂：它调用 `deepagents.create_deep_agent()` 并注入所有可注入参数（中间件、子 agent、技能、记忆、后端、检查点器）。这是唯一接触 DeepAgents 的地方。
2. **网关层（`src/scaffold/api/`）** — FastAPI Web 层。`app.py` 装配路由和中间件。`deps.py` 在 `asynccontextmanager` 生命周期内启动 LangGraph 检查点器（默认 SQLite）。路由位于 `routers/`。
3. **基础设施层（`src/scaffold/infra/`）** — 从 Deer-Flow 移植的模块：配置系统、中间件适配器、模型工厂、提示模板、通道适配器、记忆存储、结构化日志。这些与框架无关，由运行时层消费。

### 一切皆配置驱动

仓库根目录的 `config.yaml` 是唯一事实来源。它由 `AppConfig.from_file()`（`src/scaffold/infra/config/app_config.py`）加载，支持：

- **环境变量替换**：`$DEEPSEEK_API_KEY` 在加载时解析。
- **热重载**：`get_app_config()` 缓存配置并在 mtime 变化时失效。大多数配置变更无需重启服务。
- **结构化 schema**：每个顶级章节在 `src/scaffold/infra/config/` 中都有对应的 Pydantic 模型。

在中间件 kwargs 中引用配置值时，使用 `$config.memory` 或 `$env.VAR_NAME`。详见 `infra/middleware/factory.py::_resolve_kwargs()`。

### 中间件链构建（双来源）

传给 `create_deep_agent()` 的中间件来自 **两个独立来源**，在 `core/agents.py` 中拼接：

1. **Deer-Flow 适配器**：在 `config.yaml` 的 `middleware.items` 下声明。通过 `MiddlewareRegistry`（`infra/middleware/registry.py`）解析，由 `build_middleware_chain()`（`infra/middleware/factory.py`）实例化。位于 `infra/middleware/deerflow_adapters/`。
2. **DeepAgents 原生中间件**：直接在 `agents.py::_build_native_middleware()` 中构建 —— 目前为 `MemoryMiddleware` 和 `SkillsMiddleware`。

注册表将 `LoopDetectionMiddleware` 等别名映射到导入路径。也可以在 `config.yaml` 中使用完整导入路径（`mymodule:MyMiddleware`）。

### Agent 创建流程

调用 `create_agent()` 时的执行流程：

1. 加载 `AppConfig`（热重载感知）。
2. 按名称解析模型配置 → `create_chat_model()` 构建 LangChain 聊天模型。
3. 从 `config.yaml` 解析工具 → `get_available_tools()`。
4. 构建系统提示词：用户覆盖 > harness profile > 默认 scaffold 提示词。
5. 构建中间件：config 中的 Deer-Flow 适配器 + DeepAgents 原生中间件。
6. 从 config 的 `subagent_definitions` 构建子 agent。
7. 构建后端（filesystem/sandbox/composite）。
8. 用以上所有参数调用 `deepagents.create_deep_agent(...)`。
9. 将编译后的图存入 `_agent_registry`。

### 提示词组装

PromptAssembler（`infra/prompts/assembler.py`）遵循 DeepAgents 约定：**USER → BASE → CUSTOM → SUFFIX**。实际中 `agents.py::_build_system_prompt()` 目前直接从 harness profile config 组装提示词，而非通过 PromptAssembler。如果修改提示词逻辑，请与此顺序保持一致。

### 测试关键细节

测试 **必须** 将 `TestClient` 用作上下文管理器（`with TestClient(app) as client:`）。`app.py` 中的 lifespan 处理器会初始化 SQLite 检查点器并将其存入 `app.state`。没有上下文管理器时 lifespan 不会运行，依赖 `get_checkpointer()` 的路由会返回 **503** 而非预期响应。正确的 fixture 模式见 `tests/conftest.py`。

### 网关中间件堆叠顺序

在 `api/app.py` 中，中间件按「外层最后添加」的顺序注册。实际包裹顺序为：

1. CORS（最外层）
2. AuthMiddleware
3. RequestIdMiddleware
4. RateLimitMiddleware
5. LoggingMiddleware
6. ErrorHandlerMiddleware（最内层 —— 捕获所有异常）

### 添加自定义工具

在 `src/scaffold/plugins/tools/` 中创建异步可调用对象，然后在 `config.yaml` 中注册：

```yaml
tools:
  - name: my_tool
    use: scaffold.plugins.tools.my_module:my_async_function
```

函数必须是异步的，并接受与你想让 LLM 看到的 schema 匹配的关键字参数。

### 添加自定义中间件

创建一个 `AgentMiddleware` 子类。可以放在任何可导入的位置。在 `config.yaml` 中通过别名注册（如果已加入 `MiddlewareRegistry`）或完整导入路径注册：

```yaml
middleware:
  items:
    - name: mypackage.mymodule:MyMiddleware
      enabled: true
      kwargs:
        threshold: 5
```
