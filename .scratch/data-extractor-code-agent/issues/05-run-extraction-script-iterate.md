# 05: run_extraction_script 工具（迭代模式）

**What to build:** 新增执行工具，支持迭代模式：在沙箱中执行脚本，返回 stdout/stderr/退出码/输出文件/结果预览，不迁移状态不落盘工件，计入 run_count，达到 8 次后拒绝。

**Blocked by:** 1 (数据层基础), 2 (update_task_script)

**Status:** ready-for-agent

- [ ] run_extraction_script 工具实现（mode="iterate"）
- [ ] 沙箱执行：复用 bwrap，通过 INPUT_FILE/OUTPUT_FILE 环境变量传递路径
- [ ] 返回完整 stdout/stderr + 结果预览（前 N 行 + 列名）
- [ ] run_count 持久化计数：每次迭代 +1
- [ ] 达到 8 次后返回轮次超限错误
- [ ] 测试：正常执行、计数累计、超限拒绝
