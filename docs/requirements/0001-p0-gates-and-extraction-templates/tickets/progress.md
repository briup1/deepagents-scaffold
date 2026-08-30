# 工单执行台账

按时间倒序追加，一行一事（含 commit 号）。上下文压缩后信本台账与 git log，不信记忆。

## 工单 01：韧性中间件启用与事件日志

- 开工。范围见 tickets/01-resilience-middleware.md。
- 完成（97944e4）。发现：JSONFormatter 此前会静默丢弃 extra 结构化字段（telemetry 也受害），顺手修复；三个 adapter 原仅有纯文本日志，本次补齐 event/model(tool)/attempt/latency_ms/outcome 字段。
- 验证输出：`.venv/bin/ruff check src tests` → All checks passed!；`.venv/bin/pytest -q` → **379 passed**, 20 warnings in 51.63s。新增测试：model_retry 2 个（attempt 递增/recovered/耗尽逐次记录）、tool_retry 2 个（结构化事件 + 恰好重试 1 次收敛）、model_fallback 2 个（切换 fallback-1 + 全失败重抛）、JSONFormatter 2 个（extra 合并/保留字段不重复）。
- Ruling: on_failure="continue" 下重试耗尽不抛异常而是返回错误消息——验收项「全失败给可读错误」由 ToolErrorHandlingMiddleware + on_failure=continue 链路保证，已在测试 test_exhaustion/test_tool_retry_converges 覆盖 — 错了的代价：若上层另有处理会重复，目前无。
