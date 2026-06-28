# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库中工作时提供指引。

## 项目简介

基于 DeepAgents SDK + Deer-Flow 基础设施的生产级多 Agent 脚手架。支持可配置中间件、通道、记忆和链路追踪。

项目包含两个主要部分：
- **后端** (`src/scaffold/`)：Python FastAPI 服务，提供 Agent 工厂、中间件链、记忆系统
- **前端** (`src/web/`)：React 18 + TypeScript 界面，支持 SSE 流式响应

## 常用命令

```bash
# 同时启动后端与前端
bash scripts/dev.sh

# 后端命令（详见 src/scaffold/CLAUDE.md）
PYTHONPATH=src uvicorn scaffold.api.app:app --reload
pytest

# 前端命令（详见 src/web/CLAUDE.md）
cd src/web && npm run dev
```

## 技术栈与约定

- **Python**: ≥3.12
- **Web 框架**: FastAPI + Uvicorn
- **Agent 框架**: DeepAgents SDK（LangChain/LangGraph）
- **代码检查**: ruff（line-length=120, target-version=py312）
- **测试**: pytest + pytest-asyncio（asyncio_mode=auto）
- **包管理**: uv + hatchling

## 代码风格

- **命名**: snake_case（函数/变量），PascalCase（类）
- **异步**: 工具函数必须为 async
- **类型**: 完整类型注解
- **格式**: 遵循 ruff 默认规则

## 项目结构

```
deepagents-scaffold/
├── src/
│   ├── scaffold/     # 后端 Python 项目
│   └── web/          # 前端 TypeScript 项目
├── config.yaml       # 唯一配置来源（支持热重载）
├── tests/            # 后端测试
└── scripts/          # 开发脚本
```

详细项目结构请参考：
- 后端：`src/scaffold/CLAUDE.md`
- 前端：`src/web/CLAUDE.md`
