# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库中工作时提供指引。

## 项目简介

基于 DeepAgents SDK + Deer-Flow 基础设施的生产级多 Agent 脚手架。支持可配置中间件、通道、记忆和链路追踪。

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

## 技术栈与约定

- **Python**: ≥3.12
- **Web 框架**: FastAPI + Uvicorn
- **Agent 框架**: DeepAgents SDK（LangChain/LangGraph）
- **代码检查**: ruff（line-length=120, target-version=py312）
- **测试**: pytest + pytest-asyncio（asyncio_mode=auto）
- **包管理**: uv + hatchling

## 项目结构

```
src/scaffold/
├── core/          # 运行时层：DeepAgents SDK 集成
├── api/           # 网关层：FastAPI 路由与中间件
├── infra/         # 基础设施层：配置、模型、日志、通道
└── plugins/       # 扩展：自定义工具和技能
config.yaml       # 唯一配置来源（支持热重载）
```

## 代码风格

- **命名**: snake_case（函数/变量），PascalCase（类）
- **异步**: 工具函数必须为 async
- **类型**: 完整类型注解
- **格式**: 遵循 ruff 默认规则

## 分层模式

项目按三层组织，添加功能时请放入正确层级：

| 层级 | 路径 | 职责 |
|------|------|------|
| 运行时层 | `core/` | DeepAgents SDK 集成，Agent 工厂 |
| 网关层 | `api/` | FastAPI 路由、认证、限流 |
| 基础设施层 | `infra/` | 配置、模型、日志、通道（框架无关） |

**配置驱动**: `config.yaml` 是唯一事实来源，支持环境变量替换（`$ENV_VAR`）和热重载。

## 模块引用规范

三层依赖方向必须遵守：

```
core → infra  ✓（允许）
api  → infra  ✓（允许）
infra → core  ✗（禁止）
infra → api   ✗（禁止）
core ↔ api    ✗（禁止直接调用）
```

- 运行时层和网关层可依赖基础设施层
- 基础设施层不可依赖上层
- 跨层通信通过配置或接口

## 测试约定

- 使用 `TestClient` 作为上下文管理器（lifespan 依赖）
- 测试文件命名：`test_*.py`
- 测试函数命名：`test_*`
- fixture 定义在 `tests/conftest.py`
