# 02: workspace 新增 update_task_script 接口

**What to build:** ExtractionWorkspace 新增 update_task_script(task_id, content) 方法，支持子 Agent 最终脚本固化到现有任务（覆盖式），固化前做 ast.parse 语法校验。

**Blocked by:** 1 (数据层基础)

**Status:** ready-for-agent

- [ ] ExtractionWorkspace 新增 update_task_script 方法
- [ ] 固化前 ast.parse 语法校验
- [ ] 测试：正常固化、语法错误拒绝
