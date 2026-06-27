# 英文注释/文档字符串中文化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `src/scaffold/` 下所有 Python 文件的英文注释与 docstring 翻译为中文，不改动代码逻辑与字符串字面量。

**Architecture：** 按源码子目录将文件拆分为 4 组，由子代理并行翻译；主代理汇总后统一跑 lint 与测试验证。

**Tech Stack：** Python、ruff、pytest

## Global Constraints

- 仅修改 `src/scaffold/` 下的 `.py` 文件，`tests/` 不改动。
- 只翻译注释和 docstring，不改代码、变量名、函数签名、字符串字面量、日志模板、配置 key、API 路径。
- 技术术语可保留原文或直译后加括号备注（如 `checkpointer`、`CompiledStateGraph`）。
- 不添加 emoji、装饰性分隔线或额外说明。
- 翻译后必须执行 `ruff format src/scaffold`、`ruff check src/scaffold`、`pytest`。
- 每个任务完成一个可独立验证的交付物（一组文件的翻译 + 语法检查）。

---

## 文件结构

```
src/scaffold/
├── __init__.py
├── core/                         # Task 2
│   ├── __init__.py
│   ├── agents.py
│   ├── skills.py
│   ├── subagents.py
│   └── tools.py
├── api/                          # Task 3
│   ├── __init__.py
│   ├── app.py
│   ├── deps.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── error_handler.py
│   │   ├── rate_limit.py
│   │   └── request_id.py
│   └── routers/
│       ├── __init__.py
│       ├── agents.py
│       ├── health.py
│       ├── runs.py
│       ├── state.py
│       ├── threads.py
│       └── tools.py
├── infra/                        # Task 4 + Task 5
│   ├── __init__.py
│   ├── config/                   # Task 4
│   │   ├── app_config.py
│   │   ├── backend_config.py
│   │   ├── middleware_config.py
│   │   ├── model_config.py
│   │   ├── profile_config.py
│   │   ├── subagent_config.py
│   │   └── tool_config.py
│   ├── middleware/               # Task 4
│   │   ├── __init__.py
│   │   ├── factory.py
│   │   ├── registry.py
│   │   └── deerflow_adapters/
│   │       ├── __init__.py
│   │       ├── dynamic_context.py
│   │       ├── loop_detection.py
│   │       ├── safety_termination.py
│   │       ├── summarization.py
│   │       ├── title.py
│   │       ├── todo.py
│   │       ├── token_usage.py
│   │       └── tool_error_handling.py
│   ├── models/                   # Task 4
│   │   ├── factory.py
│   │   └── patched_deepseek.py
│   ├── prompts/                  # Task 5
│   │   ├── __init__.py
│   │   ├── assembler.py
│   │   ├── loader.py
│   │   └── registry.py
│   ├── channels/                 # Task 5
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── router.py
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── feishu.py
│   │       └── slack.py
│   ├── memory/                   # Task 5
│   │   ├── __init__.py
│   │   ├── storage.py
│   │   └── updater.py
│   └── logging/                  # Task 5
│       ├── __init__.py
│       ├── config.py
│       ├── middleware.py
│       └── structured.py
├── runtime/                      # Task 5
│   ├── __init__.py
│   ├── worker.py
│   └── stream_bridge/
│       ├── __init__.py
│       ├── async_provider.py
│       ├── base.py
│       └── memory.py
└── plugins/                      # Task 5
    ├── __init__.py
    ├── skills/
    │   └── __init__.py
    └── tools/
        └── __init__.py
```

---

### Task 1: 准备共享规则与文件清单

**Files:**
- 创建：`docs/superpowers/plans/2026-06-27-translate-comments.md`（本计划，已存在）
- 读取：`docs/superpowers/specs/2026-06-27-translate-comments-design.md`

**Interfaces:**
- Consumes: 设计文档
- Produces: 各子代理统一遵循的翻译规则清单

- [ ] **Step 1: 确认设计文档已审批并提交**

  检查：
  ```bash
  git log --oneline -1 docs/superpowers/specs/2026-06-27-translate-comments-design.md
  ```
  Expected: 显示包含 "Add design doc" 的提交。

- [ ] **Step 2: 准备共享翻译规则文件**

  在 `docs/superpowers/specs/2026-06-27-translate-comments-design.md` 中已有规则，无需新建。实施时代理需严格遵循：
  1. 仅翻译 `#` 注释与 `"""docstring"""`。
  2. 不改动代码、字符串字面量、日志模板、配置 key。
  3. 术语保留或括号备注。
  4. 不添加 emoji 与装饰线。

- [ ] **Step 3: 按目录拆分文件清单**

  生成 4 组文件清单（见 Task 2-5），确保无重叠、无遗漏。

---

### Task 2: 翻译 core/ 目录

**Files:**
- 修改：
  - `src/scaffold/core/__init__.py`
  - `src/scaffold/core/agents.py`
  - `src/scaffold/core/skills.py`
  - `src/scaffold/core/subagents.py`
  - `src/scaffold/core/tools.py`

**Interfaces:**
- Consumes: 共享翻译规则
- Produces: 5 个文件的中文注释与 docstring

- [ ] **Step 1: 读取并翻译所有注释/docstring**

  使用 Read 工具读取每个文件，用 Edit 工具替换英文注释为中文。注意 `agents.py` 中已有残留字符需修正。

- [ ] **Step 2: 本地语法与格式检查**

  ```bash
  ruff format src/scaffold/core
  ruff check src/scaffold/core
  ```
  Expected: `ruff check` 无错误。

- [ ] **Step 3: 提交**

  ```bash
  git add src/scaffold/core/
  git commit -m "$(cat <<'EOF'
  Translate comments and docstrings in core/ to Chinese

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3: 翻译 api/ 目录

**Files:**
- 修改：
  - `src/scaffold/api/__init__.py`
  - `src/scaffold/api/app.py`
  - `src/scaffold/api/deps.py`
  - `src/scaffold/api/middleware/__init__.py`
  - `src/scaffold/api/middleware/auth.py`
  - `src/scaffold/api/middleware/error_handler.py`
  - `src/scaffold/api/middleware/rate_limit.py`
  - `src/scaffold/api/middleware/request_id.py`
  - `src/scaffold/api/routers/__init__.py`
  - `src/scaffold/api/routers/agents.py`
  - `src/scaffold/api/routers/health.py`
  - `src/scaffold/api/routers/runs.py`
  - `src/scaffold/api/routers/state.py`
  - `src/scaffold/api/routers/threads.py`
  - `src/scaffold/api/routers/tools.py`

**Interfaces:**
- Consumes: 共享翻译规则
- Produces: 15 个文件的中文注释与 docstring

- [ ] **Step 1: 读取并翻译所有注释/docstring**

  路由文件中的 docstring 通常描述 API 行为，需准确翻译但不改变 OpenAPI 路径/参数名。

- [ ] **Step 2: 本地语法与格式检查**

  ```bash
  ruff format src/scaffold/api
  ruff check src/scaffold/api
  ```
  Expected: `ruff check` 无错误。

- [ ] **Step 3: 提交**

  ```bash
  git add src/scaffold/api/
  git commit -m "$(cat <<'EOF'
  Translate comments and docstrings in api/ to Chinese

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4: 翻译 infra/config、infra/middleware、infra/models 目录

**Files:**
- 修改：
  - `src/scaffold/infra/__init__.py`
  - `src/scaffold/infra/config/app_config.py`
  - `src/scaffold/infra/config/backend_config.py`
  - `src/scaffold/infra/config/middleware_config.py`
  - `src/scaffold/infra/config/model_config.py`
  - `src/scaffold/infra/config/profile_config.py`
  - `src/scaffold/infra/config/subagent_config.py`
  - `src/scaffold/infra/config/tool_config.py`
  - `src/scaffold/infra/middleware/__init__.py`
  - `src/scaffold/infra/middleware/factory.py`
  - `src/scaffold/infra/middleware/registry.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/__init__.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/dynamic_context.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/loop_detection.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/safety_termination.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/summarization.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/title.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/todo.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/token_usage.py`
  - `src/scaffold/infra/middleware/deerflow_adapters/tool_error_handling.py`
  - `src/scaffold/infra/models/factory.py`
  - `src/scaffold/infra/models/patched_deepseek.py`

**Interfaces:**
- Consumes: 共享翻译规则
- Produces: 22 个文件的中文注释与 docstring

- [ ] **Step 1: 读取并翻译所有注释/docstring**

  注意 Pydantic `Field(description=...)` 属于 schema 一部分，**不翻译**；仅翻译 `#` 注释与 docstring。

- [ ] **Step 2: 本地语法与格式检查**

  ```bash
  ruff format src/scaffold/infra/config src/scaffold/infra/middleware src/scaffold/infra/models
  ruff check src/scaffold/infra/config src/scaffold/infra/middleware src/scaffold/infra/models
  ```
  Expected: `ruff check` 无错误。

- [ ] **Step 3: 提交**

  ```bash
  git add src/scaffold/infra/config src/scaffold/infra/middleware src/scaffold/infra/models
  git commit -m "$(cat <<'EOF'
  Translate comments and docstrings in infra/config, middleware, models to Chinese

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 5: 翻译 infra/prompts、infra/channels、infra/memory、infra/logging、runtime、plugins 目录

**Files:**
- 修改：
  - `src/scaffold/infra/prompts/__init__.py`
  - `src/scaffold/infra/prompts/assembler.py`
  - `src/scaffold/infra/prompts/loader.py`
  - `src/scaffold/infra/prompts/registry.py`
  - `src/scaffold/infra/channels/__init__.py`
  - `src/scaffold/infra/channels/base.py`
  - `src/scaffold/infra/channels/registry.py`
  - `src/scaffold/infra/channels/router.py`
  - `src/scaffold/infra/channels/adapters/__init__.py`
  - `src/scaffold/infra/channels/adapters/feishu.py`
  - `src/scaffold/infra/channels/adapters/slack.py`
  - `src/scaffold/infra/memory/__init__.py`
  - `src/scaffold/infra/memory/storage.py`
  - `src/scaffold/infra/memory/updater.py`
  - `src/scaffold/infra/logging/__init__.py`
  - `src/scaffold/infra/logging/config.py`
  - `src/scaffold/infra/logging/middleware.py`
  - `src/scaffold/infra/logging/structured.py`
  - `src/scaffold/runtime/__init__.py`
  - `src/scaffold/runtime/worker.py`
  - `src/scaffold/runtime/stream_bridge/__init__.py`
  - `src/scaffold/runtime/stream_bridge/async_provider.py`
  - `src/scaffold/runtime/stream_bridge/base.py`
  - `src/scaffold/runtime/stream_bridge/memory.py`
  - `src/scaffold/plugins/__init__.py`
  - `src/scaffold/plugins/skills/__init__.py`
  - `src/scaffold/plugins/tools/__init__.py`

**Interfaces:**
- Consumes: 共享翻译规则
- Produces: 27 个文件的中文注释与 docstring

- [ ] **Step 1: 读取并翻译所有注释/docstring**

  `prompts/` 中若包含提示词模板字符串，仅翻译其注释，不翻译模板内容本身。

- [ ] **Step 2: 本地语法与格式检查**

  ```bash
  ruff format src/scaffold/infra/prompts src/scaffold/infra/channels src/scaffold/infra/memory src/scaffold/infra/logging src/scaffold/runtime src/scaffold/plugins
  ruff check src/scaffold/infra/prompts src/scaffold/infra/channels src/scaffold/infra/memory src/scaffold/infra/logging src/scaffold/runtime src/scaffold/plugins
  ```
  Expected: `ruff check` 无错误。

- [ ] **Step 3: 提交**

  ```bash
  git add src/scaffold/infra/prompts src/scaffold/infra/channels src/scaffold/infra/memory src/scaffold/infra/logging src/scaffold/runtime src/scaffold/plugins
  git commit -m "$(cat <<'EOF'
  Translate comments and docstrings in prompts, channels, memory, logging, runtime, plugins to Chinese

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 6: 全局验证与收尾

**Files:**
- 读取/检查：`src/scaffold/` 全部 `.py` 文件
- 不修改新文件

**Interfaces:**
- Consumes: Task 2-5 的全部修改
- Produces: 通过验证的最终工作树

- [ ] **Step 1: 全量格式化与 lint**

  ```bash
  ruff format src/scaffold
  ruff check src/scaffold
  ```
  Expected: `ruff check` 无错误。

- [ ] **Step 2: 运行测试套件**

  ```bash
  pytest
  ```
  Expected: 全部测试通过。

- [ ] **Step 3: 检查是否有遗漏英文注释**

  运行以下命令搜索可能遗漏的英文注释（需人工判断，排除保留术语与代码）：
  ```bash
  grep -RInE "^\s*# [A-Za-z]" src/scaffold/ | head -50
  ```
  Expected: 无完整英文句子注释；仅保留的术语片段可接受。

- [ ] **Step 4: 提交最终格式修复（如有）**

  若 Step 1 产生格式化差异，则提交：
  ```bash
  git add src/scaffold/
  git commit -m "$(cat <<'EOF'
  Apply final formatting after comment translation

  Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Self-Review

**1. Spec coverage:**
- 范围仅 `src/scaffold/` ✓（Task 2-5 覆盖所有子目录）
- 包含注释与 docstring ✓（Step 1 各任务明确）
- 不包含字符串字面量/日志/配置 key ✓（Global Constraints + 各 Step 1 说明）
- 术语处理 ✓（Global Constraints 第 3 条）
- 验证命令 ✓（Task 6 Step 1-2）
- 清理残留字符 ✓（Task 2 Step 1 提及 `agents.py` 残留）

**2. Placeholder scan:**
- 无 "TBD"/"TODO"/"implement later"。
- 所有命令与文件路径均为确切值。
- 每任务结束有可验证交付物。

**3. Type consistency:**
- 本计划不涉及新增类型或函数签名，无类型一致性问题。
