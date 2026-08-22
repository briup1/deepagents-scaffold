# Phase 3 实施计划：数据分析与生成式 UI

> 前置文档：`docs/superpowers/specs/2026-08-22-excel-extraction-analysis-design.md`（第 7 节「分析阶段设计」、第 11 节 Phase 3）
> 状态：Phase 1（文件上传）✅、Phase 2（三段式抽取）✅、**Phase 3（分析+生成式 UI）✅ 已完成（2026-08-22）**，完成证据见 `docs/superpowers/evidence/phase3-evidence-summary.png`。

## 1. 目标

在抽取结果（Extracted CSV 工件）之上，实现**数据分析**与**生成式 UI 展示**能力：

1. Agent 可对抽取结果执行 SQL 查询（`query_extracted_data`），回答统计/筛选类问题；
2. Agent 可根据用户自然语言需求自动决定分析方式（`analyze_extracted_data`），自行生成 SQL 或 Python 分析脚本并执行；
3. 支持多份报价单的**跨文件对比分析**（跨 CSV JOIN）；
4. 分析结果通过现有 `render_ui` 工具渲染为 `data_table` / `chart` / `metric_card` / `markdown_card`。

## 2. 设计要点（来自设计文档第 7 节）

- `query_extracted_data(extraction_id, sql)`：使用 DuckDB 直接对 CSV 执行 SQL，返回列名 + 行数据；
- `analyze_extracted_data(extraction_id, request)`：Agent 根据用户需求自行决定生成 SQL 还是 Python 分析脚本；
- 多文件对比：跨 CSV 的 SQL JOIN，如 `FROM 'ext-a.csv' AS a JOIN 'ext-b.csv' AS b ON a.pol = b.pol AND a.pod = b.pod AND a.container_type = b.container_type`；
- 会话隔离：所有 CSV 路径基于 `thread_id` 目录，查询前必须校验工件归属；
- `render_ui` 已存在（`src/scaffold/plugins/tools/generative_ui.py`），前端 Catalog 已注册 `data_table` / `chart` / `metric_card` / `download_button` / `markdown_card`（`src/web/src/catalog/index.tsx`），本阶段无需改前端组件，只需让 Agent 正确调用。

## 3. 预计涉及文件

后端（约 4 个新文件 + 3 处改动）：

| 文件 | 说明 |
|------|------|
| 新建 `src/scaffold/plugins/tools/query_extracted_data.py` | DuckDB SQL 查询工具 |
| 新建 `src/scaffold/plugins/tools/analyze_extracted_data.py` | 自然语言 → SQL/Python 分析工具 |
| 新建 `src/scaffold/plugins/skills/extraction-analysis/SKILL.md` | 分析 Skill（第 4 个 Skill） |
| 新建 `tests/test_query_extracted_data.py` | 查询工具测试 |
| 新建 `tests/test_analyze_extracted_data.py` | 分析工具测试 |
| 新建 `tests/test_analysis_e2e.py` | 工具级端到端全链路测试 |
| 修改 `config.yaml` / `config.verify.yaml` / `config.test.yaml` | 注册 2 个新工具 + 更新 `data_extractor` agent 提示词 |
| 修改 `docs/superpowers/specs/2026-08-22-excel-extraction-analysis-design.md` | Phase 3 checkbox 打勾（完成后） |

前端：无代码改动（Catalog 组件已就绪）；如做全栈验证则新建验证脚本。

## 4. 任务拆分与依赖

```
任务 1（DuckDB 查询工具 query_extracted_data）        ← 无依赖
任务 2（自然语言分析工具 analyze_extracted_data）     ← 依赖任务 1（复用查询内核）
任务 3（多文件对比分析）                              ← 依赖任务 1
任务 4（分析 Skill + Agent 提示词）                   ← 依赖任务 1、2、3
任务 5（后端测试：单测 + 工具级 E2E）                 ← 依赖任务 1-3
任务 6（配置注册与文档更新）                          ← 依赖任务 1-5
任务 7（全栈验证脚本 + E2E 测试方案执行）             ← 依赖任务 1-6
```

### 任务 1：`query_extracted_data` 工具

```python
async def query_extracted_data(
    extraction_id: str,
    sql: str,
    limit: int = 100,
) -> dict:
    """对抽取结果 CSV 执行 DuckDB SQL 查询。

    返回: {"columns": [...], "rows": [...], "row_count": N} 或 {"error": "可读错误信息"}
    """
```

实现要点：
- 通过 `ArtifactRepository` 按 `extraction_id` 查找工件，**校验 `artifact_type == "extraction"` 且 thread 上下文匹配**；
- DuckDB 对 CSV 建内存表后执行 SQL（`duckdb.sql(f"SELECT * FROM read_csv_auto('{path}')")`），避免并发锁问题（设计文档第 12 节风险项：每次查询新建连接/内存表）；
- 非法 SQL 或文件不存在时返回 `{"error": ...}`，**禁止抛异常中断 Agent**，也禁止吞掉错误——错误必须可读；
- 结果行数受 `limit` 约束，超大结果截断并提示；
- 数字/日期类型尽量原样返回（DuckDB 默认类型转换），JSON 序列化失败的值转字符串。

### 任务 2：`analyze_extracted_data` 工具

```python
async def analyze_extracted_data(
    extraction_id: str,
    request: str,
    comparison_extraction_id: str | None = None,
) -> dict:
    """根据用户自然语言需求，自动生成并执行 SQL/Python 分析。

    返回: {"columns": [...], "rows": [...], "row_count": N, "sql": "实际执行的 SQL", "summary": "一句话结论"}
    """
```

实现要点：
- MVP 采用**规则化 SQL 生成**（无需调用 LLM）：把 `request` 中的关键词映射到查询意图——`最便宜/最低` → `MIN(amount)` + ORDER BY；`平均` → `AVG`；`按 X 分组` → `GROUP BY`；`对比/比较` → 跨文件 JOIN；`数量/多少条` → `COUNT(*)`；
- 若 `comparison_extraction_id` 提供，生成跨 CSV JOIN（复用任务 3 逻辑）；
- 无法识别的需求返回 `{"error": "无法识别的分析意图，请使用：最低/平均/分组/对比/计数 等描述"}`，让 Agent 转达用户；
- 返回值带 `sql` 字段，便于 Agent 向用户展示执行过程。

### 任务 3：多文件对比分析

- 在 `query_extracted_data` / `analyze_extracted_data` 中支持 `comparison_extraction_id` 参数；
- 校验第二个工件同样属于当前 thread；
- 生成 JOIN SQL：`ON a.pol = b.pol AND a.pod = b.pod AND a.container_type = b.container_type`（列名来自两表共有列的交集，MVP 固定取 pol/pod/container_type 或由调用方传入 join_keys）；
- 对比结果同时包含 `price_a` / `price_b` / `diff`（差值）等派生列，便于 `data_table` 直接渲染。

### 任务 4：分析 Skill + Agent 提示词

- 新建 `src/scaffold/plugins/skills/extraction-analysis/SKILL.md`，内容：触发时机（用户对抽取结果提问/要求分析/要求对比）、调用 `query_extracted_data` / `analyze_extracted_data` 的规则、结果渲染规范（`render_ui` props 格式）、失败时如何向用户解释；
- 更新 `config.yaml` / `config.verify.yaml` / `config.test.yaml` 中 `data_extractor` agent 的 `system_prompt_suffix`：追加分析阶段工作流（抽取验证通过后，用户提问 → 调用分析工具 → `render_ui` 渲染）。

### 任务 5：测试

- `tests/test_query_extracted_data.py`：正常聚合查询、非法 SQL、limit 截断、非 extraction 工件拒绝、跨 thread 拒绝；
- `tests/test_analyze_extracted_data.py`：意图识别（最低/平均/分组/计数）、无法识别意图、对比模式；
- `tests/test_analysis_e2e.py`：工具级端到端全链路（见第 6 节场景 A/B/C）。

### 任务 6：配置注册与文档更新

- 三个 config 文件 `tools:` 段注册 `query_extracted_data` / `analyze_extracted_data`；
- 完成后更新设计文档 Phase 3 checkbox 打勾。

### 任务 7：全栈验证脚本

- 新建 `scripts/verify_analysis.py`（参照 `scripts/verify_data_extractor.py` 模式），用真实模型走「上传 → 抽取 → 分析 → render_ui」全链路，打印 SSE 流中的 `TOOL_CALL` 与渲染事件。

## 5. 成功标准

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| S-1 | `query_extracted_data` 对合法 SQL 返回结构化结果（columns + rows + row_count） | pytest 单测 |
| S-2 | 非法 SQL / 文件不存在返回可读 `error`，不抛异常 | pytest 单测 |
| S-3 | `analyze_extracted_data` 能识别「最低/平均/分组/计数」意图并执行 | pytest 单测 |
| S-4 | 多文件对比 JOIN 返回对比行（含双方价格列） | pytest 单测 |
| S-5 | 跨 thread 访问其他会话的 extraction_id 被拒绝 | pytest 单测 |
| S-6 | Agent 通过 `render_ui` 渲染 `data_table` / `chart` / `metric_card`，props 符合 config 组件规范 | 场景 D + 真实模型 SSE 验证 |
| S-7 | 工具级 E2E 全链路（上传→抽取→分析→渲染信封）通过 | `tests/test_analysis_e2e.py` |
| S-8 | `ruff check src tests` 通过，类型注解完整 | ruff |
| S-9 | 全部后端测试通过（含原有测试不回归） | `pytest` |
| S-10 | 真实模型下 `scripts/verify_analysis.py` 输出中可见 `TOOL_CALL(query_extracted_data)` 与 `render_ui` 调用 | 手动验证脚本 |

## 6. 端到端测试方案（重点）

### 6.1 总体策略（三层验证）

Phase 3 的「完成」需要**三层证据**，缺一不可：

| 层 | 名称 | 工具/方法 | 覆盖范围 | 是否需真实模型 |
|----|------|-----------|----------|----------------|
| L1 | 工具级 E2E（确定性） | pytest + FastAPI TestClient + DuckDB | 上传 → 抽取 → 查询/分析/对比 → render_ui 信封，含隔离与错误路径 | 否（核心证据） |
| L2 | AG-UI SSE 全链路 | `scripts/verify_analysis.py`（httpx/requests 流式消费 SSE） | 真实模型驱动 Agent 完成「分析 + 渲染」决策链 | 是（验收证据） |
| L3 | 全栈前端冒烟 | Playwright 或手动（`verify_dev.sh` + 浏览器） | 前端 Catalog 已注册组件可渲染分析结果 | 否（mock 模型即可） |

> 说明：`config.verify.yaml` 的 mock 模型（`MockChatModel`）**不会调用工具**（`bind_tools` 仅返回自身），因此 L2 无法用 mock 模式替代；L1 不依赖模型，是自动化回归的核心；L2 是"Agent 真的会按流程分析"的最终证明。

### 6.2 L1：工具级 E2E（`tests/test_analysis_e2e.py`）

固定数据：用 `simple_quote.xlsx`（仓库根目录已有：3 行报价，列 = 报价单号/起运港/目的港/船公司/柜型/海运费(USD)/有效期/航程(天)/备注）或测试内构造的确定性样例（参照 `tests/test_preview_excel.py` 的 `_make_excel_bytes`）。

**场景 A：单文件 SQL 聚合查询**

| 项 | 内容 |
|----|------|
| 前置 | 上传 Excel（thread=t-ana）→ `generate_extraction_code` → `execute_extraction_code` 得到 `extraction_id`，断言抽取成功 |
| 操作 | `query_extracted_data(extraction_id=..., sql="SELECT 目的港, MIN(海运费) AS min_price FROM data GROUP BY 目的港 ORDER BY min_price")` |
| 断言 | 返回 `columns == ["目的港", "min_price"]`；`rows` 中洛杉矶行 `min_price == 1450`（simple_quote 中 COSCO 深圳→洛杉矶 1450）；`row_count == 3` |

**场景 B：自然语言分析**

| 项 | 内容 |
|----|------|
| 前置 | 同上 |
| 操作 | `analyze_extracted_data(extraction_id=..., request="哪条航线到洛杉矶最便宜？")` |
| 断言 | 返回含 `sql` 字段；`rows[0]` 是到洛杉矶的最低价行；`summary` 非空 |

**场景 C：多文件对比**

| 项 | 内容 |
|----|------|
| 前置 | 上传两份 Excel（同结构不同价格），各自抽取得到 `ext_a`、`ext_b` |
| 操作 | `analyze_extracted_data(extraction_id=ext_a, request="对比两份报价单相同航线的价格", comparison_extraction_id=ext_b)` |
| 断言 | 返回行同时含双方价格列；同 pol/pod 的行数 == 两份文件匹配行数；差值列存在 |

**场景 D：render_ui 信封**

| 项 | 内容 |
|----|------|
| 前置 | 场景 A 结果在手 |
| 操作 | 直接调用 `render_ui(type="data_table", props={"title": "最低运价", "columns": [...], "rows": [...]})` |
| 断言 | 返回 `{"generative_ui": {"type": "data_table", "props": {...}, "surfaceId": None}}`；props 的 columns/rows 均为对象数组（符合 config 组件规范，而非 preview_excel 的字符串数组） |

**场景 E：错误与隔离路径**

| 编号 | 场景 | 断言 |
|------|------|------|
| E-1 | `query_extracted_data` 传入非法 SQL（如 `SELEC *`） | 返回 `{"error": ...}`，不抛异常 |
| E-2 | 传入不存在的 extraction_id | 返回可读 `error` |
| E-3 | 传入 `artifact_type != "extraction"` 的工件（如 upload） | 返回 `error`，拒绝执行 |
| E-4 | thread=t1 的工具调用访问 t2 的 extraction_id | 返回 `error`（会话隔离） |

### 6.3 L2：AG-UI SSE 全链路（`scripts/verify_analysis.py`）

工具与方法：`requests` 流式消费 `/agent/data_extractor` 的 SSE；参照 `scripts/verify_data_extractor.py` 的 `_print_sse_stream`，额外统计 `TOOL_CALL` / `TOOL_RESULT` / `RUN_FINISHED` / `RUN_ERROR` 事件。

前置条件：
1. `config.yaml` 配置真实模型且 API Key 已就绪；
2. `bash scripts/dev.sh` 启动后端（8000）与前端（3000）。

验证场景（人工执行，输出作为验收证据）：

```bash
uv run python scripts/verify_analysis.py
```

脚本流程：
1. 构造 3 行运价样例 Excel（可复用 `verify_data_extractor.py` 的 `_build_sample_excel`）；
2. `POST /api/files/upload`（thread=thread-verify-xxx）→ 得 `artifact_id`；
3. 第一轮消息：「请抽取 carrier、pol、pod、container_type、amount 字段」→ 等待抽取链路完成（Agent 会依次调用 4 个抽取工具）；
4. 第二轮消息：「用 query_extracted_data 分析一下到 Los Angeles 的航线中哪个最便宜，并用 data_table 展示」；
5. 断言输出中出现：
   - `TOOL_CALL query_extracted_data`（或 `analyze_extracted_data`）且 result 非空；
   - `TOOL_CALL render_ui` 且 args 中 `type == "data_table"`；
   - `RUN_FINISHED` 正常出现，`RUN_ERROR` 不出现。

退出码：任一断言失败返回非 0，便于接入 CI/人工检查。

### 6.4 L3：全栈前端冒烟（Playwright / 手动）

前置：`bash scripts/verify_dev.sh`（mock 模型，无需真实 API Key）。

验证内容（证明前端渲染链路就绪，可与 Phase 3 后端能力衔接）：
1. 打开 `http://localhost:3000`，聊天框拖拽上传 `simple_quote.xlsx` → 出现文件卡片；
2. 用 Playwright（项目已有 `.playwright-mcp` 基础设施）或手动检查 `src/web/src/catalog/index.tsx` 中 `data_table` / `chart` / `metric_card` / `download_button` 已注册且 schema 完整（`tests` 中 `createCatalog.test.tsx` / `Chart.test.tsx` 已覆盖渲染）；
3. 可选：在 mock 模式下手动调 `render_ui` 信封（通过 API 层注入）确认组件能渲染——若做此步，把用例补进 `src/web` 前端测试。

> 说明：mock 模型不触发工具调用，L3 只证明「前端已具备渲染分析结果的能力」，不证明 Agent 分析链路——后者由 L2 承担。

### 6.5 验收命令（一条命令逐步执行）

```bash
# 1) 后端静态检查
ruff check src tests && ruff format src tests

# 2) 全部后端测试（含新增 3 个测试文件 + 原有测试不回归）
pytest -v

# 3) 只跑 Phase 3 相关测试（快速回归）
pytest tests/test_query_extracted_data.py tests/test_analyze_extracted_data.py tests/test_analysis_e2e.py -v

# 4) 前端构建/测试（如改动了前端）
cd src/web && npm run build && npm test

# 5) 真实模型全链路（需 config.yaml 真实 API Key）
bash scripts/dev.sh
uv run python scripts/verify_analysis.py
```

### 6.6 完成判定（Phase 3 验收清单）

> ✅ 已于 2026-08-22 全部达成，证据见 `docs/superpowers/evidence/`。

- [x] S-1 ~ S-7 全部通过（L1 自动化证据：`tests/test_analysis_e2e.py` 等 18 用例）
- [x] `ruff check src tests` 通过（S-8）
- [x] `pytest` 全量通过，无原有测试回归（S-9：278 passed）
- [x] `scripts/verify_analysis.py` 在真实模型下输出含 `TOOL_CALL(query_extracted_data)` 与 `render_ui`（S-10，L2 证据：`phase3-l2-verify-output.txt`）
- [x] L3 前端冒烟通过（Playwright 真实浏览器：`phase3-l3-chat-result.png` 渲染出 data_table）
- [x] 设计文档 Phase 3 checkbox 全部打勾

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 真实模型不可用（无 API Key），L2 无法执行 | 中 | L1 自动化证据独立成立；L2 作为可选的验收证据，接入 CI 时可用带工具调用脚本的增强 mock（后续可选任务：给 `MockChatModel` 增加按脚本调工具的 `tool_call_script` 模式） |
| DuckDB 对中文列名/类型推断不稳定 | 中 | 工具内部统一转字符串输出；测试用中文列名样例覆盖 |
| 自然语言意图识别（规则版）覆盖不全 | 中 | 返回可读 error 让 Agent 转达用户；后续可升级为 LLM 生成 SQL |
| 大结果集序列化性能 | 低 | limit 截断 + 提示 |

## 8. 建议下一步

1. 按任务 1 → 7 顺序实施（任务 1 无依赖，可先行）；
2. 完成 L1 后先跑 `pytest tests/test_query_extracted_data.py tests/test_analyze_extracted_data.py tests/test_analysis_e2e.py -v` 锁定核心能力；
3. 再补配置注册与 Agent 提示词（任务 4、6）；
4. 最后用真实模型执行 L2 验收（任务 7），并把 `verify_analysis.py` 纳入日常验证流程。
