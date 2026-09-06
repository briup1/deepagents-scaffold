# 部署验证技能


## 概述
服务启动或变更上线后执行验证，确认服务可用、依赖正常。

## 触发条件
`scripts/dev.sh` / `scripts/verify_dev.sh` 启动后，或后端变更部署到任一环境后自动激活。

## 执行步骤

### Step 1: 环境健康检查
- `curl -s http://localhost:8000/health` 返回 `{"status": "healthy"}`。
- `logs/` 无启动期致命错误；配置热重载无异常。

### Step 2: API 冒烟测试
- 按 `wiki/接口协议.md` 核心接口清单跑冒烟：`/api/agents/`（鉴权与非鉴权路径）、`/api/threads/` CRUD、`/agent` SSE 端点（用 curl `-N` 验证事件流首包）。
- 前端 `http://localhost:3002` 页面可访问，构建无类型错误（`npm run build`）。

### Step 3: 基础设施依赖验证
- SQLite 数据目录 `data/` 可写，`migrate()` 正常建表。
- 沙箱可用：`scripts/setup_bwrap_apparmor.sh`（Ubuntu 23.10+）已按需执行；`config.verify.yaml` mock 模式下端到端路径走通。

### Step 4: 监控告警确认
- 关键指标无异常飙升（错误率/延迟/token 消耗）。
- 追踪（LangSmith/Langfuse，可选启用）通道畅通。

## 输出
- 验证报告：每项通过/失败；失败项附现场信息并立即回滚（`git revert` + 重启，见 `rules/开发流程规范.md` 第 6 节回滚策略）。
