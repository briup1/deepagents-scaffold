# 工单 04：前端 token 接入

**阻塞**：02 | **对应需求**：R1-2（前端半） | **设计契约**：design.md 3.8

## 范围

- localStorage 键 `scaffold_token` 存取；无 token 时显示一次性 token 输入界面
- 全部 REST 请求（`api/threads.ts`、文件上传/下载）带 `X-API-Key` 头
- `HistoryHttpAgent` 构造传 `headers: { "X-API-Key": token }`（SSE 链路）
- 任意请求收到 401 → 清空 localStorage 回到 token 输入界面
- 前端测试：header 注入与 401 回退流程

**不含**：后端认证（02/03）、新增 UI 组件（模板确认沿用现有 button_group，属 06）。

## 验收（G/W/T）

- [ ] Given 无本地 token，When 打开前端，Then 显示 token 输入界面而非聊天界面
- [ ] Given 已输入有效 token，When 发送消息 / 加载历史 / 下载工件，Then 所有请求（含 SSE）带 `X-API-Key` 头且正常返回
- [ ] Given token 失效（后端 401），When 任意请求收到 401，Then 自动清空 token 并回到输入界面
- [ ] Given 改动完成，When 运行 `cd src/web && npm run build && npm test`，Then 构建与测试全部通过
