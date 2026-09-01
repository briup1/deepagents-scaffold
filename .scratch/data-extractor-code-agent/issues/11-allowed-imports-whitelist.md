# 11: 全局 allowed_imports 配置列全量白名单

**What to build:** execution_sandbox.allowed_imports 配置替换为全量白名单（pandas/openpyxl/numpy/csv/json/re/os/sys/time/pathlib/functools/warnings 等）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 更新 config.yaml 的 allowed_imports
- [ ] 测试：沙箱内所有必要模块可导入
