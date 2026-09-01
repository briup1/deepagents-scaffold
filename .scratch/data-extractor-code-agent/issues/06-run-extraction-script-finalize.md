# 06: run_extraction_script 工具（收口模式）

**What to build:** run_extraction_script 支持收口模式：执行脚本后迁移状态 code_generated → validating，落盘 extraction 工件，不计入 run_count。

**Blocked by:** 5 (run_extraction_script 迭代模式)

**Status:** ready-for-agent

- [ ] run_extraction_script 收口模式实现（mode="finalize"）
- [ ] 迁移状态：code_generated → validating
- [ ] 落盘 extraction 工件，挂接 task.extracted_artifact_id
- [ ] 不计入 run_count
- [ ] 测试：收口执行、状态迁移、工件落盘
