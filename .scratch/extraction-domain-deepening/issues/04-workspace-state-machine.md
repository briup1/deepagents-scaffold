# 04: Workspace 状态机方法 + execute 工具接入

**What to build:** Extraction Task 的状态机获得唯一载体。Extraction Workspace 新增两个方法：`transition_task`（声明期望的前置状态与目标状态；守卫失败返回与现有工具错误响应同构的 error dict；成功时刷新时间戳并持久化）和 `fail_task`（构造 Validation Report、置 failed、持久化、返回工具错误响应）。execute 工具——目前守卫 if 与两段近乎复制粘贴的失败仪式所在地——率先改由这两个方法驱动，守卫与失败仪式全部删除。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] 五个状态（goal_setting / code_generated / validating / success / failed）× 合法/非法流转的矩阵在 workspace 层有穷尽测试（fake repository）
- [x] `fail_task` 的响应结构有测试：报告内容、failed 状态、错误 dict 三者一致
- [x] execute 工具中不再出现状态守卫 if 与内联的 `task.status = ...` 赋值
- [x] execute 工具对外行为不变（含错误响应形状），现有测试不改断言仍通过
- [x] `pytest` 全量通过；`ruff check src tests` 通过
