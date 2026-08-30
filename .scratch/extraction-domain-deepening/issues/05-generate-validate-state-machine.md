# 05: generate + validate 工具接入状态机

**What to build:** 剩余两个抽取工具（generate、validate）改用 Extraction Workspace 的 `transition_task` / `fail_task`。至此，Extraction Task 的全部状态流转规则只有一个归属模块；五个工具全部退化为薄编排，抽取域深化（B1+B2）完成。

**Blocked by:** 04: Workspace 状态机方法 + execute 工具接入

**Status:** done

- [x] generate 与 validate 工具中不再出现状态守卫 if、内联 `task.status = ...` 赋值、手写失败 Validation Report 构造
- [x] 全仓库范围内，任务状态赋值只发生在 workspace 的状态机方法内（grep 静态验证）
- [x] 两个工具对外行为不变，现有工具级测试不改断言仍通过
- [x] `pytest` 全量通过；`ruff check src tests` 通过
- [x] spec（docs/superpowers/specs/2026-08-29-extraction-domain-deepening-spec.md）中 Out of Scope 各项未被触碰
