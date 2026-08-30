# 工单 07：集成验收与收尾

**阻塞**：01、03、04、05、06 | **对应需求**：全部 + Out of Scope 核对 | **设计契约**：design.md 全文

## 范围

- 全量验证：`.venv/bin/ruff check src tests && .venv/bin/pytest`、`cd src/web && npm run build && npm test`
- `bash scripts/verify_dev.sh` 启动后跑端到端验收脚本（curl 实测，输出贴进台账）：
  - 无凭证访问 `/api/threads`、`/api/files/{id}/download`、`/agent/{agentId}` SSE → 401
  - 错误 token → 401；`/health` 无凭证 → 200
  - alice/bob 双 token 交叉访问会话与文件 → 403
  - 带 token 的 SSE 请求正常流式返回
- Out of Scope 核对（需求文档 9 条逐条确认未越界，含：无遗留用户、无迁移脚本、无 Docker 依赖、无完整账号系统/RBAC、无密钥托管、无 UI 版指纹规则配置）
- 合并前 code review
- requirement.md 状态置 `done`（+HTML chip），回写总览；design.html/requirement.html 状态同步

**不含**：新功能开发。

## 验收（G/W/T）

- [ ] Given 全部前置工单完成，When 运行全量测试与构建命令，Then 全部通过（输出贴台账）
- [ ] Given 验证模式服务运行中，When 执行端到端验收脚本，Then 全部断言通过（输出贴台账）
- [ ] Given 需求文档 Out of Scope 清单，When 逐条核对代码与配置，Then 无越界实现（git diff 佐证）
- [ ] Given code review 完成，When 审查意见处理完毕，Then requirement 状态置 `done`、文档与 HTML 同步
