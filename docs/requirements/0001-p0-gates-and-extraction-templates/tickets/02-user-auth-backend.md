# 工单 02：多用户认证与身份透传（后端）

**阻塞**：无 | **对应需求**：R1-1、R1-2（认证半） | **设计契约**：design.md 3.1 / 3.2 / 3.3

## 范围

- `infra/config/app_config.py` 新增 `AuthConfig`（`enabled` + `users[{user_id, token}]`，token 支持 `$env.` 前缀，启动时解析）；config.yaml 增加 `auth` 段；`.env.example` 增加 `SCAFFOLD_TOKEN_ALICE` 等示例
- 重写 `api/middleware/auth.py`：token→user_id 映射、**移除 `/agent` 豁免**（豁免仅 /health、/docs、/redoc、/openapi.json）、认证通过置 `request.state.user_id`；`SCAFFOLD_API_KEY` 单 key 模式移除
- `infra/context.py` 新增 `user_id_ctx` + `get_current_user_id()`（与 request_id 同款 contextvars 模式）；`api/routers/agents.py` 在创建流式任务前 set
- `api/deps.py` 新增归属校验依赖函数（统一出口，供 03 使用）
- 移除 `/agent` 单 Agent 别名路由（用户既有决策：彻底不保留）
- 认证关闭（`enabled: false` 或 users 为空）时全放行且 user_id 一律为 `"default"`

**不含**：仓储层 user_id 过滤与 403 归属落地（03）、前端（04）。

## 验收（G/W/T）

- [ ] Given auth.enabled=true 且配置两个用户，When 请求 `/agent/{id}`（SSE）、`/api/threads`、`/api/agents` 不带凭证或带错误 token，Then 一律 401
- [ ] Given 同上，When 带 alice 的 token 请求以上端点，Then 放行且 `get_current_user_id()` 在 Agent 工具链路内读到 `"alice"`
- [ ] Given 同上，When 请求 `/health`，Then 无需凭证返回 200
- [ ] Given auth 未启用，When 任意请求，Then 全放行且 user_id 为 `"default"`（本地开发向后兼容）
- [ ] Given token 配置为 `$env.XXX` 但环境变量缺失，When 启动服务，Then 启动失败并明确报出缺失的变量名（token 不落盘）
- [ ] Given 别名已移除，When `POST /agent`（无 agentId），Then 404（不再可用）
- [ ] Given 改动完成，When 运行 `.venv/bin/ruff check src tests && .venv/bin/pytest`，Then 全部通过（含新增认证测试）
