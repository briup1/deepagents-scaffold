# 工单执行台账

按时间倒序追加，一行一事（含 commit 号）。上下文压缩后信本台账与 git log，不信记忆。

## 工单 01：韧性中间件启用与事件日志

- 开工。范围见 tickets/01-resilience-middleware.md。
- 完成（97944e4）。发现：JSONFormatter 此前会静默丢弃 extra 结构化字段（telemetry 也受害），顺手修复；三个 adapter 原仅有纯文本日志，本次补齐 event/model(tool)/attempt/latency_ms/outcome 字段。
- 验证输出：`.venv/bin/ruff check src tests` → All checks passed!；`.venv/bin/pytest -q` → **379 passed**, 20 warnings in 51.63s。新增测试：model_retry 2 个（attempt 递增/recovered/耗尽逐次记录）、tool_retry 2 个（结构化事件 + 恰好重试 1 次收敛）、model_fallback 2 个（切换 fallback-1 + 全失败重抛）、JSONFormatter 2 个（extra 合并/保留字段不重复）。
- Ruling: on_failure="continue" 下重试耗尽不抛异常而是返回错误消息——验收项「全失败给可读错误」由 ToolErrorHandlingMiddleware + on_failure=continue 链路保证，已在测试 test_exhaustion/test_tool_retry_converges 覆盖 — 错了的代价：若上层另有处理会重复，目前无。

## 工单 02：多用户认证与身份透传（后端）

- 完成（待提交）。实现：AuthConfig（enabled+users，token $env 严格解析——auth 路径下缺失环境变量启动即 ValueError 并报变量名，其余路径保持空串兼容）；AuthMiddleware 重写为 token→user_id 映射（/agent 豁免移除，SCAFFOLD_API_KEY 单 key 模式移除）；user_id_ctx 透传（ag_ui 端点 set）；deps.get_request_user_id；移除 /agent 别名（前端 App.tsx 同步改为恒用 /agent/{name}）；config.yaml auth 段 enabled:true（alice/bob），config.verify.yaml 固定测试 token，config.test.yaml 无 auth（默认放行）；.env 追加本地开发 token（随机生成）。
- Ruling: 全局 $env 解析对 auth 段改为严格报错（带路径跟踪 ~6 行），而非全局限错——其余 $VAR（如未配置的 ANTHROPIC_API_KEY）仍允许缺失 — 为什么：生产配置引用不存在的 provider key 不应阻断启动，但 token 缺失是安全事故 — 错了的代价：若未来有其他安全配置段需同样严格，需扩展路径判断。
- Ruling: /agent 别名移除波及测试 5 处 + 前端 1 处（App.tsx 单 agent 场景恒用 /agent/default），同步修掉 — 需求文档未列此项，依据用户此前拍板决策执行。
- 验证输出：`.venv/bin/ruff check src tests` → All checks passed!；`.venv/bin/pytest -q` → **389 passed**, 20 warnings in 50.43s；`npm run build` → ✓ built in 23.56s；`npm test` → 84 passed。新增测试：AuthMiddleware 10 个（多用户映射/401/豁免/“/agent 不豁免”）、AuthConfig 7 个（校验/严格 env 解析）。

## 工单 05：bubblewrap 沙箱 provider

- 完成（待提交）。实现：BwrapSandbox（继承 SubprocessSandbox 复用 AST 扫描；--unshare-all --unshare-net --die-with-parent --clearenv + ro-bind /usr//lib//lib64//bin + venv 根目录 + ro-bind 输入/脚本 + bind 输出 + tmpfs /tmp + chdir /work/out；内存沿用 RLIMIT_AS preexec_fn；超时沿用 asyncio kill）；extra_env 宿主机路径前缀自动映射为沙箱内路径；factory 注册 bwrap；config.yaml/config.verify.yaml provider=bwrap（config.test.yaml 保持 subprocess 保证测试密闭）；scripts/setup_bwrap_apparmor.sh（幂等，含冒烟验证）；README 部署前置说明。
- Ruling: BwrapSandbox 继承而非并列 SubprocessSandbox——零成本复用 AST 白名单作第一道闸（实测探针脚本 import urllib 被拦），bwrap 为第二道 — 错了的代价：两层耦合，若未来要纯 bwrap 无 AST 需拆分。
- 验证输出：`.venv/bin/pytest tests/infra/test_bwrap_sandbox.py -v` → **7 passed**（正常脚本产出一致 / 隔离探针 etc+输入写+宿主机项目全 BLOCKED / AST 拒 urllib / 256MB 限额 MemoryError / 2s 超时 kill exit=-1 / extra_env 路径映射 / bwrap 缺失可读错误）；`sudo bash scripts/setup_bwrap_apparmor.sh` 两次执行均 OK 且冒烟通过（幂等实测）；全量 `.venv/bin/ruff check src tests` 通过、`.venv/bin/pytest -q` → **396 passed**。
- 排障记录：_bindings_ok 初版只挂 /usr 导致 /bin/true 的动态链接器（/lib64）缺失误判 skip，补齐 /bin /lib /lib64 后正常。
