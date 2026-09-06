# 单元测试编写技能


## 概述
为业务逻辑编写有效单元测试：有断言、可重复、Mock 干净。

## 触发条件
新功能编码完成、或修复 bug 时激活。

## 执行步骤

### Step 1: 测试范围识别
- 覆盖：业务分支、边界条件、异常路径。
- 核心模块（`scaffold/api`、`scaffold/runtime`、`scaffold/infra`，对应核心链路）必须全覆盖；纯 getter/框架胶水代码不写测试。

### Step 2: 测试环境准备
- 外部依赖（LLM 调用、沙箱、文件系统、真实 SQLite 之外的状态）全部 Mock / 临时目录隔离。
- `conftest.py` 提供统一 fixture；FastAPI 用 `TestClient` 上下文管理器（lifespan 依赖）。
- 前端 jsdom 环境，mock `fetch`。

### Step 3: 测试用例编写
- 命名表达场景：`test_<行为>_<条件>`（如 `test_create_thread_returns_404_for_foreign_user`）。
- 每个用例：准备 → 执行 → 断言（禁止无断言测试）。
- 断言要具体：比较期望值，禁止只断言"不为 None/不为 null"。
- 异常分支、边界值（空/零/超长/非法 token）各至少一例。

### Step 4: 测试执行与验证
- `pytest` / `npm test` 全部通过；核心模块覆盖率对照 `rules/开发流程规范.md` 门槛（≥60% ❓）。

### Step 5: 测试文档输出
- 复杂用例加一行注释说明业务背景。

## 反模式（禁止）
- 只调不断言；测试里 sleep 等待；测试间共享可变状态；为凑覆盖率写无意义断言。
