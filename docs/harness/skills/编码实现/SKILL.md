# 编码实现技能


## 概述
按标准流程实现功能编码，确保架构合规、红线零违反。

## 触发条件
需求分析已确认、进入编码阶段时激活。

## 前置条件
- 已读项目根 `CLAUDE.md`（红线）与 `rules/` 相关章节。
- 已读本次任务相关的 `wiki/`（业务模型/接口协议/数据模型）。

## 后端编码步骤（顺序执行，Python / FastAPI 变体）

### Step 1: Schemas（Pydantic 模型）
- 在 `infra/` 对应模块定义请求/响应/实体模型；全量类型注解，禁止裸 `dict` 传业务数据。
- 敏感字段（金额等）注意精度与校验器。

### Step 2: Repository（数据访问）
- 在 `infra/history/` 或 `infra/artifacts/` 增加仓库方法；表结构变更写入 `migrate()`（`PRAGMA user_version` 递增）。
- 查询注意索引与 `user_id` 隔离；多步写入有回滚路径。

### Step 3: Service / 装配（runtime / core）
- 业务逻辑放对层：Agent 装配进 `runtime/agents.py`，工具进 `plugins/tools/`，中间件进 `infra/middleware/`。
- 新组件必须在 `config.yaml` 注册后由工厂装配，禁止工厂硬编码。
- 阻塞 IO 不得堵 event loop（丢线程池或 async 化）。

### Step 4: Router（api/routers/）
- 路由 + 参数校验 + `response_model`；只组装不实现业务。
- 错误交给 `ErrorHandlerMiddleware`，路由内不吞异常。

### Step 5: 异常与日志
- 边界条件全覆盖；日志带 `request_id`，关键操作可审计；禁止敏感信息入日志（红线 9）。

## 前端编码步骤（顺序执行）

### Step 1: API 封装
- 按 `wiki/接口协议.md` 在 `src/api/` 新增封装，走 `apiFetch`/`apiFetchJson`，类型对齐响应结构。

### Step 2: 类型定义
- 请求/响应类型与被测结构紧挨着定义；未知结构 `unknown` + 收窄。

### Step 3: 组件实现
- 页面组件组装子组件；数据逻辑下沉 `hooks/`；遵守语法红线（函数组件、Tailwind、无 any）。

### Step 4: 测试与验证
- 自测主路径 + 错误路径；准备单元测试素材。

## 输出
- 代码 + 自测记录 + 对 wiki/rules 的疑似更新点（交给 harness-sync）。
