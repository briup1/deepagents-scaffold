# 工单 03：用户级数据隔离落地（后端）

**阻塞**：02 | **对应需求**：R1-2（归属半）、R1-3、R1-4 | **设计契约**：design.md 3.3 / 3.4

## 范围

- DB schema 重建（版本号递增）：`threads` / `artifacts` / `extraction_tasks` 增加 `user_id NOT NULL` 列；**删除 data/ 存量数据**（需求已确认直接删除，无迁移脚本）
- 三个仓储类全方法以 user_id 为一级过滤维度（签名见 design.md 3.4）；`Artifact` 模型增 `user_id`
- 路由接入 02 的归属校验依赖：`GET /api/threads/{id}`、`GET /api/threads/{id}/messages`、`GET /api/files/{artifact_id}/download` 等，非属主一律 403
- Agent 工具层（上传/预览/抽取等六工具）经 `get_current_user_id()` 过滤

**不含**：认证本身（02）、前端（04）、模板（06）。

## 验收（G/W/T）

- [ ] Given alice 与 bob 各有会话/工件/抽取任务，When bob 请求 alice 的会话详情、消息、文件下载，Then 一律 403
- [ ] Given 同上，When bob 列出会话/工件/任务，Then 列表中零条 alice 的数据
- [ ] Given 同上，When bob 通过 Agent 工具访问 alice 的资源，Then 工具返回结构化错误且服务端日志有完整拒绝记录
- [ ] Given 升级前 data/ 存在旧数据，When 本工单部署步骤执行，Then data/ 被清空、新 schema 生效，启动不报错
- [ ] Given 改动完成，When 运行 `.venv/bin/ruff check src tests && .venv/bin/pytest`，Then 全部通过（含新增隔离测试：跨用户访问全部 403）
