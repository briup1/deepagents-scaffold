---
id: 0001
slug: p0-gates-and-extraction-templates
status: approved
created: 2026-08-30
source: docs/requirements/0001-p0-gates-and-extraction-templates/requirement.md（已批准）
chosen: 方案 A（bubblewrap 本地沙箱）——2026-08-30 用户指定并经端到端验证通过
---

# 方案设计 0001：P0 三道闸门 + 抽取模板复用

## 1. 需求↔方案映射

| 需求子项 | 方案模块 | 覆盖 |
|----------|----------|------|
| R1-1 用户级身份凭证（轻量，配置驱动） | M1a 多用户认证中间件（扩展 `AuthMiddleware` + `auth.users` 配置） | ✅ |
| R1-2 全部业务端点身份校验 + 资源归属 403 | M1a（移除 `/agent` 豁免）+ M1b 路由层归属校验 | ✅ |
| R1-3 Agent 工具层按用户过滤 | M1c `user_id_ctx` 上下文 + 仓储层 user_id 过滤 | ✅ |
| R1-4 存量数据直接删除 | M1d 清空 `data/` 重建 schema（无迁移脚本） | ✅ |
| R2-1 隔离执行环境（fs/网络/资源底线） | M2 新沙箱 provider（候选 bwrap / e2b，见第 5 节） | ✅ |
| R2-2 工件经仓储流转，沙箱不直连 DB | 沿用现状架构（工具层读写仓储，沙箱只收 input/output 目录） | ✅ 复用 |
| R2-3 启动失败/超时/OOM 结构化错误 | M2 `SandboxResult` 错误映射（沿用现有 `execute_extraction_code` 转换层） | ✅ |
| R3-1 模型重试默认启用 | M3 `config.yaml` 启用 `ModelRetryMiddleware`（代码/测试已就绪） | ✅ 复用 |
| R3-2 主模型失败回退备用模型 | M3 启用 `ModelFallbackMiddleware` + `fallback_models` 配置 | ✅ 复用 |
| R3-3 工具重试收敛 1 次 | M3 启用 `ToolRetryMiddleware`（`max_retries: 1`，与注释默认值一致） | ✅ 复用 |
| R3-4 重试/回退事件结构化日志 | M3a 三个 adapter 增加事件日志（model/attempt/latency/outcome） | ✅ |
| R4-1 抽取模板实体（目标+脚本+指纹，归属用户） | M4a `extraction_templates` 表 + `ExtractionTemplateRepository` | ✅ |
| R4-2 验证通过后询问保存（UI 按钮确认） | M4b `save_extraction_template` 工具 + 现有 button_group | ✅ |
| R4-3 上传后指纹匹配→确认→复用脚本→验证 | M4c `match_extraction_template` 工具 + 复用现有执行/验证链路 | ✅ |
| R4-4 模板管理最小集（列出/重命名/删除） | M4b `list/rename/delete_extraction_template` 工具 | ✅ |
| R4-5 模板用户隔离 | M4a 表含 `user_id`，仓储强制过滤 | ✅ |
| R4-6 不匹配/复用失败回退完整流程 | M4c Agent 流程规则（skill 提示词）+ 工具返回结构化失败原因 | ✅ |

无遗漏；方案模块与需求为多对多关系（M1a 覆盖 R1-1/R1-2，M4a 覆盖 R4-1/R4-5）。

## 2. 前后对比

### 用户视角

| 场景 | 现在 | 设计后 |
|------|------|--------|
| 多人使用 | 无身份概念，知道 thread_id 即可看他人全部数据 | 每人一个 token；只能看到/操作自己的会话、工件、模板；他人资源 403 |
| 模型 429/超时 | Agent 直接报错死亡 | 自动重试 → 自动切备用模型 → 全失败才显示「服务暂时不可用」 |
| 同格式报价单二次抽取 | 重新走 6-8 次交互的目标对齐 | 选模板 + 确认，≤2 次交互出验证通过结果 |
| 生成代码执行 | 直接在宿主机跑（能读 /etc、能联网） | 隔离环境：只读输入 + 可写输出，禁网，超限即杀 |

### 系统视角

现状链路：

```
浏览器 ──无认证──► /agent SSE ──► Agent ──► 六工具 ──► 仓储(thread_id 隔离)
                        │                      └────► SubprocessSandbox(宿主机裸奔)
浏览器 ──单key(豁免/agent)──► /api/files/{id}/download ──► 无归属校验
config.yaml: 韧性中间件整段注释（未启用）
```

设计后链路（**加粗 = 新增**，其余 = 复用/改动）：

```
浏览器 ──token──► AuthMiddleware(token→user_id, /agent 不再豁免)
                        │ request.state.user_id
                        ├─────► /agent SSE ──► user_id_ctx ──► Agent 工具 ──► 仓储(user_id+thread_id 两级过滤)
                        │                                          │
                        │                                          ├────► 【BwrapSandbox/E2BSandbox】(隔离执行)
                        │                                          └────► 【模板工具组】(save/match/list/rename/delete)
                        ├─────► /api/threads|files|agents ──► 归属校验(403)
                        └─────► /api/files/{id}/download ──► 归属校验(403)
Agent 链路内: ModelRetry → ModelFallback → ToolRetry（默认启用）→ 【事件结构化日志】
DB: threads/artifacts/extraction_tasks 增 user_id 列；【extraction_templates 新表】；存量清空重建
```

## 3. 接口与契约设计

### 3.1 认证配置（config.yaml 新增 `auth` 段）

```yaml
auth:
  enabled: true
  users:
    - user_id: alice
      token: $env.SCAFFOLD_TOKEN_ALICE   # token 支持 $env. 前缀，启动时解析
    - user_id: bob
      token: $env.SCAFFOLD_TOKEN_BOB
```

- `enabled: false` 或 `users` 为空 → 全放行，`user_id` 一律为 `"default"`（本地开发向后兼容）
- `SCAFFOLD_API_KEY` 单 key 模式废弃，由 `auth.users` 取代（token 即原 API key 语义 + 身份）

### 3.2 AuthMiddleware 行为契约（改动 `src/scaffold/api/middleware/auth.py`）

| 情况 | 行为 |
|------|------|
| 无 `X-API-Key` 或 token 未注册 | 401 `{"detail": "Invalid or missing API key"}` |
| token 已注册 | `request.state.user_id = 对应 user_id`，放行 |
| 豁免路径 | 仅 `/health`、`/docs`、`/redoc`、`/openapi.json`（**移除 `/agent` 豁免**） |

### 3.3 用户上下文（改动 `src/scaffold/infra/context.py`）

```python
user_id_ctx: ContextVar[str] = ContextVar("scaffold_user_id", default="default")
def get_current_user_id() -> str: ...
```

`/agent*` SSE 端点在创建流式任务**之前** `user_id_ctx.set(request.state.user_id)`（contextvars 随 asyncio 任务传播，工具层经 `get_current_user_id()` 读取，与现有 request_id 透传同一模式）。

### 3.4 仓储层契约（user_id 一级维度）

存量数据删除 → 直接以 v2 schema 重建（`user_id TEXT NOT NULL`），无迁移脚本：

```python
# HistoryRepository
async def ensure_thread(self, thread_id: str, agent_id: str, user_id: str) -> None
async def get_thread(self, thread_id: str, user_id: str) -> ThreadDetail | None   # 非本人 → None → 路由层 403
async def list_threads(self, user_id: str, ...) -> ThreadsListResponse
async def get_messages(self, thread_id: str, user_id: str) -> list[ThreadMessage]

# ArtifactRepository / Artifact
Artifact 增字段 user_id: str
async def list_by_thread(self, thread_id: str, user_id: str, ...)

# ExtractionTaskRepository：create / list / get 均带 user_id
```

路由层统一规则：资源不存在或 **不属于当前用户** → 404/403；归属校验集中在各 router 的依赖函数（`api/deps.py`）完成，避免每个端点各写一份。

### 3.5 抽取模板（新增）

```sql
CREATE TABLE extraction_templates (
    template_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    goal TEXT NOT NULL,          -- Extraction Goal JSON（字段/类型/约束/示例行）
    script TEXT NOT NULL,        -- 验证通过的抽取脚本源码
    fingerprint TEXT NOT NULL,   -- 结构指纹 JSON
    source_file_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_templates_user ON extraction_templates(user_id);
```

结构指纹（复用 `preview_excel` 已返回的 `sheet_names`/`columns` 计算）：

```json
{"sheets": ["报价单"], "columns": {"报价单": ["品名","单价","数量"]}, "signature": "sha256(sheets+columns) 前 16 位"}
```

匹配规则：`signature` 完全一致才算候选（保守方向，需求方已确认）；否则判定不匹配。

新工具组（全部 async + 关键字参数，user_id 取自 `user_id_ctx`，注册进 `config.yaml`）：

```python
async def save_extraction_template(task_id: str, name: str) -> dict
    # 仅当 task.status == success；从任务取 goal + script + 来源文件指纹
async def match_extraction_template(artifact_id: str) -> dict
    # → {"matched": true, "template": {...}} 或 {"matched": false, "reason": "..."}
async def list_extraction_templates() -> list[dict]
async def rename_extraction_template(template_id: str, name: str) -> dict
async def delete_extraction_template(template_id: str) -> dict
```

复用执行路径：Agent 从 `match` 结果取 `template.script`，写入工作区后走**现有** `execute_extraction_code` → `validate_extraction_result` 链路，不新增执行工具；任一步失败 → 工具返回结构化原因，Agent 按 skill 提示词规则回退完整六步流程并告知用户。保存确认沿用现有 Generative UI `button_group`（前端零新增组件）。

### 3.6 沙箱（新增 provider，`src/scaffold/infra/sandbox/`）

```python
class BwrapSandbox(Sandbox):
    async def run(self, script_path: Path, input_dir: Path, output_dir: Path,
                  timeout: int = 60, memory_limit_mb: int = 512,
                  extra_env: dict[str, str] | None = None) -> SandboxResult
```

命令骨架（与 `Sandbox` ABC 现有签名完全对齐）：

```
bwrap --unshare-all --unshare-net --die-with-parent \
  --ro-bind <python 运行时目录> ... \
  --ro-bind <input_dir> /work/in --bind <output_dir> /work/out \
  --tmpfs /tmp --chdir /work \
  /usr/bin/python3 /work/in/<script>
```

- 内存限制沿用 RLIMIT_AS 方式（与 `SubprocessSandbox` 相同机制，子进程继承）
- 超时沿用现有 asyncio timeout + kill
- `execution_sandbox.provider: bwrap` 注册进 `factory.get_sandbox`；`docker`/`e2b` 占位保持
- 错误映射：bwrap 启动失败（如 userns 被禁）、RLIMIT 触发的 MemoryError、超时 kill → `SandboxResult(exit_code, stderr)`，由 `execute_extraction_code` 现有转换层输出可读信息
- **部署前置（一次性提权，三选一）**：安装放行 bwrap 的 AppArmor profile（**本机已采用**，`/etc/apparmor.d/bwrap-userns`，侵入最小）/ `chmod u+s /usr/bin/bwrap` / `sysctl kernel.apparmor_restrict_unprivileged_userns=0`

### 3.7 韧性中间件（config.yaml 启用 + 日志增强）

```yaml
- name: ModelFallbackMiddleware
  enabled: true
  kwargs:
    models: $config.models
    fallback_models: [<config.models 中真实备用模型名>]
- name: ModelRetryMiddleware
  enabled: true
  kwargs: {max_retries: 2, backoff_factor: 2.0, initial_delay: 1.0, max_delay: 60.0, jitter: true, retry_on_status_codes: [429, 502, 503, 504]}
- name: ToolRetryMiddleware
  enabled: true
  kwargs: {max_retries: 1, ...}   # 幂等未知工具收敛为 1 次
```

三个 adapter 增加结构化事件日志（字段：`event=model_retry|model_fallback|tool_retry`、`model`、`attempt`、`latency_ms`、`outcome`），复用 `infra/logging`；`config.verify.yaml` 以 mock 模型覆盖 fallback 目标。

### 3.8 前端契约（`src/web`）

- localStorage 键 `scaffold_token`；无 token 显示一次性输入界面
- 全部 fetch（`api/threads.ts`、上传/下载）带 `X-API-Key` 头
- `HistoryHttpAgent` 构造传入 `headers: {"X-API-Key": token}`（已验证 `@ag-ui/client` HttpAgent 配置支持 `headers?: Record<string, string>`，见 6.1）
- 401 响应 → 清空 localStorage 回到 token 输入界面

## 4. 历史资产复用分析

| 资产 | 路径 | 复用方式 |
|------|------|----------|
| AuthMiddleware | `src/scaffold/api/middleware/auth.py` | 扩展：单 key → token 映射 + user_id 注入 |
| contextvars 透传模式 | `src/scaffold/infra/context.py`（request_id/trace_id 同款） | 新增 `user_id_ctx`，零新机制 |
| Sandbox ABC + 工厂占位 | `src/scaffold/infra/sandbox/base.py`、`factory.py`（docker/e2b 槽位已在） | 新增 provider 实现即可，接口不动 |
| SubprocessSandbox 的 RLIMIT/超时机制 | `src/scaffold/infra/sandbox/subprocess_sandbox.py` | BwrapSandbox 照搬限制机制 |
| 三个韧性 adapter + 注册表 + 测试 | `src/scaffold/infra/middleware/deerflow_adapters/`、`registry.py`、`tests/test_middleware.py` | 代码就绪，仅启用 + 日志增强 |
| `$config.models` / `$env.` 引用解析 | `src/scaffold/infra/middleware/factory.py` | fallback_models/auth token 直接复用该语义 |
| preview_excel 输出 | `src/scaffold/plugins/tools/preview_excel.py`（已返回 sheet_names/columns） | 指纹计算的现成输入，工具不改 |
| execute_extraction_code 错误转换层 | `src/scaffold/plugins/tools/execute_extraction_code.py` | 模板复用与沙箱错误的可读化出口，不改 |
| button_group 确认组件 | `src/web/src/catalog/`（Generative UI 现有） | 模板保存/复用确认，零新增前端组件 |
| ExtractionWorkspace 封装 | `src/scaffold/infra/extraction/workspace.py` | 模板仓储并入同一生命周期 |

**从零开发（仅两项，均有理由）**：`extraction_templates` 表与仓储（新实体，无既有资产）；`BwrapSandbox`（既有 docker/e2b 仅为 `NotImplementedError` 占位，无可复用实现）。

## 5. 多方案并列：R2 沙箱选型

| 维度 | 方案 A：bubblewrap 本地沙箱 | 方案 B：e2b 托管沙箱 |
|------|----------------------------|----------------------|
| 隔离能力 | fs/网络/资源全隔离（Linux namespaces） | 全隔离（云端 microVM） |
| 本机可用性 | ⚠️ 当前被 AppArmor userns 限制拦截，需一次性提权配置（见 6.1 实测） | ✅ 不受本机限制，注册即得 API key |
| 成本 | 零 | 按量计费（免费额度有限） |
| 网络依赖 | 无（完全离线） | 每次执行依赖外网 |
| 数据出域 | 不出本机 | 文件需上传第三方云（报价单含商业敏感） |
| 新增依赖 | 无（bwrap 已装于 /usr/bin/bwrap） | `uv add e2b` |
| 部署耦合 | 目标机需同款提权配置 | 目标机需外网 + key 管理 |

**已选定：方案 A**（用户指定，2026-08-30 经端到端验证通过，见第 6/7 节）。方案 B 作为配置可切换的备选保留（`Sandbox` ABC 已隔离差异），适用于完全拿不到提权条件的部署环境。

## 6. 审查结论（附证据）

### 6.1 可行性

- ✅ 韧性中间件代码与测试就绪：执行 `uv run pytest tests/test_middleware.py -q` → `25 passed, 1 warning in 0.05s`
- ✅ bwrap 端到端验证**通过**（2026-08-30 实测）。前置配置：经 sudo 安装 AppArmor 放行 profile `/etc/apparmor.d/bwrap-userns`（内容：`/usr/bin/bwrap flags=(unconfined) { userns, }`，`apparmor_parser -r` 加载）——这是三条提权路径中侵入最小的一条（不关闭全局限制、不给 bwrap setuid）。配置后探针结果（输出原文）：

  ```
  read_etc_passwd: BLOCKED (FileNotFoundError)   # /etc 未挂载
  network: BLOCKED (URLError)                    # --unshare-net 生效
  write_input_dir: BLOCKED (OSError)             # --ro-bind 只读输入
  read_host_project: BLOCKED (FileNotFoundError) # 宿主机项目目录未挂载
  write_output_dir: OK  /  read_input_dir: OK    # 工作区语义正确
  mem_512mb: BLOCKED (MemoryError)               # prlimit --as=256MB 生效
  timeout 3s kill: exit=124，无残留进程            # --die-with-parent 生效
  ```

  结论：方案 A 成立。目标部署机需同款一次性配置（Ubuntu 24.04：安装同款 AppArmor profile 即可）。
- ✅ HttpAgent 支持自定义 headers：`grep headers node_modules/@ag-ui/client/dist/index.d.ts` → `headers?: Record<string, string>;`
- ✅ e2b 未安装（`import e2b` → ImportError），选方案 B 时 `uv add e2b`

### 6.2 复用性

- 第 4 节每项资产均附真实路径并经读取核实；从零开发仅 2 项（模板实体、BwrapSandbox），理由已写明。

### 6.3 规范性

- 分层依赖：新代码落在 `infra/sandbox`（bwrap）、`infra/context`（user_id_ctx）、`infra/extraction`（模板仓储）、`plugins/tools`（模板工具）、`api/middleware`（auth）——符合 `core→infra`、`api→infra`，无反向依赖
- 新工具全部 async + 关键字参数；Python 全类型注解；沿用 ruff（line-length=120）
- 密钥不落库不落 config：token 走 `$env.` 引用
- 未执行：前端构建/测试（设计阶段未改前端代码，留待实施期验证）

## 7. 最小验证

**风险点**：方案里最悬的假设是"bwrap 能在目标机器上跑起来"——Linux 沙箱隔离依赖 unprivileged user namespaces，而 Ubuntu 23.10+ 默认用 AppArmor 限制它。若不可行，方案 A 就是空中楼阁。

**验证方法**：第一步复现拦截（三种 unshare 入口均被拒，根因 `apparmor_restrict_unprivileged_userns=1`）；第二步用侵入最小的提权路径（安装放行 bwrap 的 AppArmor profile）解除限制；第三步跑完整探针——读 `/etc/passwd`、联网、写只读输入目录、读宿主机项目目录、写工作区、256MB 内存限额、3 秒超时 kill。实验代码在 /tmp/bwrap_poc，用完即弃。

**结果与证据**：见 6.1——七项隔离底线全部符合预期（敏感资源 BLOCKED、工作区读写 OK、限额与超时生效、无残留进程）。

**结论（大白话）**：**可行。** 这台机器的门锁是 Ubuntu 默认的 AppArmor 规则，装一条只放行 bwrap 的规则（不动全局设置）就开了。开门后沙箱表现完全符合要求：恶意脚本读不到宿主机文件、连不了网、写不出工作区、吃多了内存会被杀、超时会被杀干净。目标部署机照抄这一条规则即可。
