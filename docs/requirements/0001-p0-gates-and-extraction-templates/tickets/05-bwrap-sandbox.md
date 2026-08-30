# 工单 05：bubblewrap 沙箱 provider

**阻塞**：无 | **对应需求**：R2-1 / R2-2 / R2-3 | **设计契约**：design.md 3.6；可行性证据见 design.md 6.1（七项探针已通过）

## 范围

- 新增 `src/scaffold/infra/sandbox/bwrap_sandbox.py`：`BwrapSandbox` 实现 `Sandbox` ABC（`--unshare-all --unshare-net --die-with-parent` + ro-bind 输入 + bind 输出 + tmpfs /tmp + `--chdir /work`；内存沿用 RLIMIT_AS（prlimit 包装），超时沿用 asyncio timeout + kill）
- `infra/sandbox/factory.py` 注册 `bwrap`；`app_config.SandboxExecutionConfig.provider` 文档更新；config.yaml `execution_sandbox.provider: bwrap`；docker/e2b 占位保留
- 部署脚本 `scripts/setup_bwrap_apparmor.sh`（写 `/etc/apparmor.d/bwrap-userns` profile + `apparmor_parser -r`，需 sudo，幂等）+ README 部署前置说明
- E2E 测试：沙箱内跑探针脚本，断言读 `/etc/passwd` 失败、联网失败、写输入目录失败、写输出目录成功（bwrap 不存在时 skip，保证 CI 可过）

**不含**：docker/e2b 实现、模板（06）、韧性（01）。

## 验收（G/W/T）

- [ ] Given `execution_sandbox.provider=bwrap`，When 抽取流程执行脚本，Then 脚本在 bwrap 命名空间内运行，正常脚本产出结果与现状一致
- [ ] Given 同上，When 脚本尝试读 `/etc/passwd`、访问外网、写输入目录，Then 全部失败并映射为可读错误信息（非沙箱崩溃/裸堆栈）
- [ ] Given 脚本超时或超内存，When 限制触发，Then 进程被杀死且无残留，返回结构化错误（超时/OOM 可区分）
- [ ] Given 全新 Ubuntu 24.04 机器，When 以 sudo 执行 `scripts/setup_bwrap_apparmor.sh`，Then bwrap userns 可用（脚本幂等，重复执行不报错）
- [ ] Given 改动完成，When 运行 `.venv/bin/ruff check src tests && .venv/bin/pytest`，Then 全部通过
