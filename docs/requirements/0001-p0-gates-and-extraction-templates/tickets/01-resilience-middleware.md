# 工单 01：韧性中间件启用与事件日志

**阻塞**：无 | **对应需求**：R3-1 / R3-2 / R3-3 / R3-4 | **设计契约**：design.md 3.7

## 范围

- config.yaml 取消注释并启用 `ModelFallbackMiddleware` / `ModelRetryMiddleware` / `ToolRetryMiddleware`；`fallback_models` 指向 config.yaml 中真实存在的模型（`kimi-for-coding`）；ToolRetry `max_retries: 1`
- 三个 adapter（`src/scaffold/infra/middleware/deerflow_adapters/`）日志增强：每次重试/回退输出结构化字段 `event`（model_retry/model_fallback/tool_retry）、`model`、`attempt`、`latency_ms`、`outcome`，复用 `infra/logging`
- `config.verify.yaml` 同步启用并以 mock 模型作为 fallback 目标
- 新增测试断言结构化日志字段

**不含**：认证/用户隔离（02/03）、沙箱（05）、模板（06）、前端。

## 验收（G/W/T）

- [ ] Given 默认 config.yaml 启动，When Agent 模型调用返回 429，Then 自动重试最多 2 次，日志含 `event=model_retry` 且 `attempt` 递增、`model`/`latency_ms`/`outcome` 字段齐全
- [ ] Given 主模型重试耗尽仍失败，When 再次调用，Then 自动切换到 `kimi-for-coding`，日志含 `event=model_fallback`（用 mock/fake 模型模拟，不打真实 API）
- [ ] Given 主模型与回退模型全部失败，When 重试与回退均耗尽，Then 用户侧收到可读错误信息（非堆栈/原始异常文本）
- [ ] Given 工具调用抛出可重试错误，When ToolRetry 生效，Then 恰好重试 1 次后收敛，日志含 `event=tool_retry`
- [ ] Given 改动完成，When 运行 `.venv/bin/ruff check src tests && .venv/bin/pytest`，Then 全部通过
