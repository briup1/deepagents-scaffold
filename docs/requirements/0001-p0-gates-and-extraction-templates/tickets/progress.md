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

## 工单 03：用户级数据隔离落地（后端）

- 完成（待提交）。实现：threads/artifacts/extraction_tasks 三表增 user_id NOT NULL 列 + 索引；旧 schema 守卫（缺 user_id 列即 RuntimeError 指引删 data/，PRAGMA user_version=2）；HistoryRepository.ensure_thread/get_thread(新)/list_threads(user_id)/delete_thread(user)/delete_threads_by_agent(user)；Artifact/ExtractionTask 模型增 user_id（默认 default）；仓储 list/delete 全部 user 过滤；workspace 工具层经 get_current_user_id() 过滤（get_task/get_artifact 跨用户→None + logger.warning 拒绝日志）；REST 路由归属校验（threads 详情/消息/删除、files 详情/下载 403，列表过滤，上传撞他人会话 403，create_thread 显式 ID 撞占 403）；ag_ui SSE 端点 ensure_thread 带 user + 劫持校验（他人 thread_id → 403 不流式）；存量 data/ 已删（其中 AGENTS.md/skills 为运行时再生文件，已确认非 git 跟踪）。
- Ruling: workspace 内部直接读 get_current_user_id() 而非工具逐个传参——调用点 5 个工具零改动 — 为什么：与 request_id 透传同模式，ctx 已是既定机制 — 错了的代价：后台任务无 ctx 时归 default 用户，auth 关闭环境行为与现状一致。
- Ruling: 跨用户访问 REST 详情返 403（需求明确），列表过滤为空（不泄露存在性的同时满足"列表零条"验收）；仓储 get 不过滤、过滤在 workspace/路由层——REST 需要区分 404/403 — 错了的代价：直连仓储的新代码需自行比较 user_id。
- 排障：① 删 data/ 后 tmp_tests 目录也被删（config.test.yaml sqlite_dir=./tmp_tests/data），aiosqlite 不建目录 → workspace.__aenter__ 补 mkdir parents；② REST 测试共享 session 级 DB 文件，固定 id 播种撞 UNIQUE → 改 uuid 后缀；③ conn fixture 漏 migrate extraction_tasks（delete_thread 级联依赖）。
- 验证输出：`.venv/bin/ruff check src tests` → All checks passed!；`.venv/bin/pytest -q` → **409 passed**（新增 test_isolation.py 13 个：REST 403×4 场景/列表不可见/自有资源不受影响/仓储过滤×4/workspace ctx 隔离+拒绝日志×2/旧 schema 守卫×2）；`npm run build` ✓ built；`npm test` 84 passed。

## 工单 04：前端 token 接入

- 完成（待提交）。实现：src/api/auth.ts（localStorage 持久化 + apiFetch 统一注入 X-API-Key + 401 全局登出订阅）；threads/files/copilotkit 三个 API 模块全部改走 apiFetch；HistoryHttpAgent 构造传入 headers（SSE /agent 请求带 token）；App.tsx 无 token 即渲染 TokenGate 输入页（提交后清空错误态重拉）；useThreads 依赖 token 重拉；新增 A1-A3 认证测试（无 token 显示输入页、输入后进入且请求带头、401 清 token 回输入页）。
- Ruling: 无 token 无条件显示输入页（而非仅 401 后）——按工单验收字面执行；后端 auth 关闭时请求头被忽略，两种模式都安全 — 代价：auth 关闭的纯开发模式也需先输入任意 token。
- Ruling: apiFetch 在无 token 时保持原生 fetch 调用签名（不包 init），既有调用方测试零改动。
- 排障：① 首次 /api/agents/ 在输入页期间即发起（无 token）→ effect 加 !token 早退；② A3 测试在 render 后才装 401 mock → 挂载期请求已用旧 mock 成功，改为 render 前安装。
- 验证输出：`npm run build` ✓ built；`npm test` **94 passed**（新增 A1-A3 三个认证场景 + auth.test.ts 6 个单测）；后端 `.venv/bin/pytest -q` 409 passed 无回归。

## 工单 06：抽取模板复用

- 完成（待提交）。实现：extraction_templates 表（design.md 3.5 字段+索引，signature 索引走 json_extract）+ ExtractionTemplateRepository（get/find_by_signature/list/rename/delete 全部 user_id 强制过滤）；ExtractionTemplate 模型；infra/extraction/fingerprint.py（openpyxl 读 sheet 名+各 sheet 表头列 → canonical JSON → sha256 前16位）；workspace 生命周期挂 template_repo + save_template_from_task/match_template/list_templates/rename_template/delete_template（user_id 取 user_id_ctx，跨用户按不存在处理）；5 个工具（async+关键字参数）注册进 config.yaml/config.verify.yaml；generate_extraction_code 增加可选 script 参数（复用模板脚本，不新增执行工具）；data_extractor 提示词流更新（上传先 match→命中确认后复用→失败回退完整流程；验证通过后 button_group 询问保存）。
- Ruling: 复用路径不加新执行工具，给 generate_extraction_code 加可选 script 覆盖——与 design 3.5 "从 match 取 template.script 走现有 execute/validate 链路"一致 — 代价：generate 的 schema 多一个可选字段。
- Ruling: 模板 fingerprint 由 workspace 现场计算（复用 preview_excel 同源 openpyxl 逻辑但独立实现）——预览不落库结构信息，避免改 preview 返回值契约。
- 排障：① find_by_signature 同时间戳并列 → ORDER BY 追加 created_at DESC, rowid DESC；② HistoryRepository.migrate 现在对 extraction_templates 也做 _assert_user_id_schema（新表天然通过，旧库无此表直接跳过）。
- 验证输出：`.venv/bin/ruff check src tests` → All checks passed!；`.venv/bin/pytest -q` → **418 passed**（新增 test_extraction_templates.py 9 个：指纹稳定性/列序敏感/仓储 CRUD+签名取最新+隔离/workspace 保存需 success/保存-命中-未命中回环/跨用户不可见）；config.yaml 加载验证：5 工具已注册、data_extractor profile 存在。

## 工单 07：集成验收与收尾

- 完成。全量验证：`.venv/bin/ruff check src tests` All checks passed!；`.venv/bin/pytest -q` **418 passed**；`npm run build` ✓ built；`npm test` **94 passed**。
- 端到端验收（config.verify.yaml + mock 模型，实测 curl 输出）：
  - 无凭证 /api/threads=401、/api/agents=401、/agent/coding SSE=401；错误 token=401；/health 无凭证=200
  - alice 建会话+传 xlsx 后：bob get thread=403、bob get messages=403、bob download=403、bob 列表 total=0；alice download own=200
  - 带 alice token SSE /agent/coding 正常流式（RUN_STARTED + RAW on_chain_start 事件）；POST /agent（无 agentId）=404
- OOS 9 条逐条核对（git diff 97944e4~1..HEAD 佐证，67 文件无 rbac/oauth/billing/market/version/channel/pdf/docx/migration 越界文件）：RBAC 未引入（仅 user_id 列+归属校验）；认证仍为配置化 token 列表无注册流；存量无迁移（旧 schema 启动拒绝+data/ 已删）；无计费；模板强 user_id 过滤无共享；模板仅 rename/delete 无编辑版本；上传仍限 xlsx/xls（E2E 实测 txt 被拒）；通道侧零改动；thread_id 语义未改。
- 代码审查（安全点）：SCAFFOLD_API_KEY 全部移除无残留；auth 中间件无 token 日志；豁免仅 /health /docs /redoc /openapi.json；隔离在仓储/路由/workspace 三层强制；沙箱联网/内存/超时由工单05 探针测试覆盖。意见：无阻塞项。
- requirement.md status: implementing → **done**；requirement.html chip 同步 Done · 已完成。
