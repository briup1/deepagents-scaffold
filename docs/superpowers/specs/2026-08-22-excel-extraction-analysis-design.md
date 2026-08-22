# Excel 报价单抽取与分析系统设计

## 1. 背景与目标

### 1.1 背景

客户会收到供应商提供的国际海运报价单 Excel 文件，通常包含数千行不同航线的运价信息。客户不希望人工阅读，而是希望借助 Agent 的能力：

1. 从 Excel 中按需求抽取结构化数据；
2. 对抽取结果进行验证，确保准确；
3. 基于抽取结果进行问答、检索、统计分析和对比分析；
4. 通过表格和图表等生成式 UI 展示结果。

### 1.2 设计目标

- 支持用户在聊天框中拖拽上传 Excel 文件；
- 支持 Agent 通过三段式 Skill 完成抽取：目标对齐 → 代码生成 → 结果验证；
- 支持迭代优化：验证不通过时回到代码生成或目标对齐阶段；
- 原始文件、生成脚本、抽取结果均作为**本会话工件**保存，不落业务数据库；
- 支持 Agent 对抽取结果执行 SQL/Python 分析，并通过 `data_table` / `chart` 组件渲染；
- 严格保证用户隔离和会话隔离。

---

## 2. 核心概念与术语

| 术语 | 定义 |
|------|------|
| **Artifact / 工件** | 本会话中产生的所有文件，包括原始上传文件、生成的抽取脚本、抽取结果 CSV 等。 |
| **Upload File / 上传文件** | 用户从聊天框上传的原始 Excel 文件。 |
| **Extraction Task / 抽取任务** | 一次从原始文件到 CSV 结果的全过程，包含目标、脚本、结果、验证报告等状态。 |
| **Extraction Goal / 抽取目标** | 用户希望从文件中抽取的内容描述，包括字段要求、约束、示例等。 |
| **Extraction Script / 抽取脚本** | Agent 生成的 Python 脚本，用于从原始 Excel 中读取并输出 CSV。 |
| **Extracted CSV / 抽取结果** | 抽取脚本执行后生成的结构化 CSV 文件，作为后续分析的输入。 |
| **Validation Report / 验证报告** | Skill 3 对抽取结果进行比对后生成的报告，标明通过项和异常项。 |
| **Session-scoped / 会话作用域** | 所有工件和抽取任务仅对当前 `thread_id` 可见，其他会话无法访问。 |

---

## 3. 用户旅程

```
用户打开聊天 → 拖拽上传 Excel
    ↓
Agent 调用 preview_excel 预览文件结构
    ↓
用户描述想抽取的字段和规则（Skill 1）
    ↓
Agent 生成抽取 Python 脚本（Skill 2）
    ↓
Agent 调用 execute_extraction_code 执行脚本，生成 CSV
    ↓
Agent 调用 validate_extraction_result 进行验证（Skill 3）
    ↓
验证通过？
    ├─ 是 → 抽取完成
    └─ 否 → 回到 Skill 2（改脚本）或 Skill 1（改目标/预期值）
    ↓
用户提问 / 要求分析 / 要求对比
    ↓
Agent 生成 SQL / Python 分析脚本
    ↓
Agent 调用 render_ui(data_table / chart) 展示结果
```

---

## 4. 系统架构

### 4.1 新增模块

```
src/scaffold/
├── api/
│   └── routers/
│       └── files.py          # 文件上传 / 下载 / 列表 API
├── core/
│   └── tools/                # 核心工具实现（可放在 plugins/tools/ 下）
│       ├── file_preview.py
│       ├── extraction_code.py
│       ├── extraction_execute.py
│       ├── extraction_validate.py
│       ├── data_query.py
│       └── data_analyze.py
├── infra/
│   ├── artifacts/            # 工件存储与元数据管理
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── storage.py
│   └── sandbox/              # 代码执行沙箱抽象
│       ├── base.py
│       └── subprocess_sandbox.py  # MVP 实现
```

### 4.2 数据流

```
┌──────────┐     upload      ┌──────────────┐
│  Frontend │ ───────────────► │ /api/files   │
└──────────┘                  └───────┬──────┘
                                      │ save to data/artifacts/{thread_id}/uploads/
                                      ▼
                               ┌────────────┐
                               │ FileRecord  │
                               │ (metadata) │
                               └─────┬──────┘
                                     │ file_id
                                     ▼
┌─────────────────────────────────────────────────────┐
│                    Agent Tools                       │
│  preview_excel(file_id)                              │
│  generate_extraction_code(file_id, requirements)     │
│  execute_extraction_code(code, file_id)              │
│  validate_extraction_result(...)                     │
│  query_extracted_data(file_id, sql)                  │
│  analyze_extracted_data(file_id, request)            │
└─────────────────────────────────────────────────────┘
                                     │
                                     ▼
                            data/artifacts/{thread_id}/
                            ├── scripts/
                            ├── extractions/
                            └── reports/
```

---

## 5. 文件与工件存储

### 5.1 目录结构

```
data/artifacts/{thread_id}/
├── uploads/
│   └── {upload_id}-{original_name}
├── scripts/
│   └── {script_id}.py
├── extractions/
│   └── {extraction_id}.csv
└── reports/
    └── {report_id}.csv
```

- 所有路径以 `thread_id` 作为一级目录，天然实现会话隔离；
- 文件名使用随机 ID，避免路径遍历和特殊字符问题；
- 同一用户的不同会话之间完全隔离。

### 5.2 元数据表

在 SQLite 历史库中新增 `artifacts` 表，用于追踪工件：

```sql
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,        -- upload | script | extraction | report
    original_name TEXT,                 -- 上传文件原始名
    stored_path TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    metadata TEXT,                      -- JSON: 关联 task_id, parent_id 等
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
);

CREATE INDEX idx_artifacts_thread_id ON artifacts(thread_id);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);
```

### 5.3 抽取任务表

```sql
CREATE TABLE extraction_tasks (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    upload_artifact_id TEXT NOT NULL,
    status TEXT NOT NULL,              -- goal_setting | code_generated | validating | success | failed
    requirements TEXT,                 -- Skill 1 目标描述
    script_artifact_id TEXT,
    extracted_artifact_id TEXT,
    validation_report TEXT,            -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
    FOREIGN KEY (upload_artifact_id) REFERENCES artifacts(artifact_id),
    FOREIGN KEY (script_artifact_id) REFERENCES artifacts(artifact_id),
    FOREIGN KEY (extracted_artifact_id) REFERENCES artifacts(artifact_id)
);
```

---

## 6. 工具与 Skill 设计

### 6.1 Skill 1：设立抽取目标

**目的**：让 Agent 与用户充分对齐抽取需求。

**触发方式**：用户上传 Excel 后，Agent 主动进入本 Skill。

**典型输出**：

```json
{
  "task_id": "ext-001",
  "requirements": {
    "file_id": "upload-001",
    "description": "从报价单中提取各航线价格",
    "fields": [
      {"name": "carrier", "description": "船公司", "required": true},
      {"name": "pol", "description": "起运港", "required": true},
      {"name": "pod", "description": "目的港", "required": true},
      {"name": "container_type", "description": "箱型", "required": true},
      {"name": "amount", "description": "报价金额", "type": "number", "required": true}
    ],
    "constraints": [
      "只提取有效期在 2025-01-01 之后的记录",
      "忽略表头前 3 行的说明文字"
    ],
    "expected_samples": [
      {"carrier": "MSC", "pol": "SHANGHAI", "pod": "LOS ANGELES", "container_type": "40HQ", "amount": 3200}
    ]
  }
}
```

**工具**：
- `preview_excel(file_id, sheet_index=0, limit=20)`：返回 sheet 列表、列名、前 N 行样本。

### 6.2 Skill 2：编写并执行抽取代码

**目的**：Agent 生成 Python 脚本并执行，输出 CSV。

**工具**：
- `generate_extraction_code(file_id, requirements)`：返回可执行的 Python 脚本字符串。
- `execute_extraction_code(code, file_id, task_id)`：在沙箱中执行脚本，生成 CSV 工件，返回 `extraction_id`。

**脚本约束**：
- 脚本读取 `/mnt/input/{file_id}.xlsx`（沙箱内挂载路径）；
- 脚本输出 `/mnt/output/{extraction_id}.csv`；
- 仅允许使用 `pandas`, `openpyxl`, `numpy`, `csv`, `json`, `re` 等白名单库；
- 禁止网络访问、禁止写入非输出目录、禁止执行 shell。

### 6.3 Skill 3：验证抽取结果

**目的**：将实际抽取值与目标值比对。

**目标值来源**（组合 D）：
- 用户在 Skill 1 中提供的示例行；
- 用户在 Skill 1 中描述的字段规则（类型、非空、范围等）；
- Agent 根据原始文件抽样判断的期望结果；
- 历史成功经验（后续可选）。

**工具**：
- `validate_extraction_result(task_id, rules)`：
  - 读取 `extracted_artifact_id` 对应的 CSV；
  - 按规则校验：字段是否存在、类型是否正确、示例行是否一致、非空约束是否满足；
  - 返回验证报告。

**验证报告格式**：

```json
{
  "passed": false,
  "summary": "5 项检查中 3 项通过",
  "checks": [
    {"rule": "字段 carrier 存在", "status": "pass"},
    {"rule": "字段 amount 为数值", "status": "fail", "details": "12 行无法转换为数字"},
    {"rule": "示例行一致", "status": "pass"}
  ],
  "suggestion": "建议清洗 amount 列中的非数字字符后重新抽取"
}
```

### 6.4 迭代循环

```
Skill 1 (Goal) ──► Skill 2 (Code) ──► Skill 3 (Validate)
    ▲                    │                  │
    └────────────────────┴──────────────────┘
              验证失败时返回优化
```

- 验证失败时，Agent 优先回到 Skill 2，基于上一次脚本做增量修改；
- 当问题涉及字段理解错误时，可回到 Skill 1 重新对齐目标或修改预期值；
- 每次迭代都会更新 `extraction_tasks` 表中的 `status` 和 `validation_report`；
- MVP 阶段脚本生成后立即执行，不增加“先展示再确认”的交互步骤。

---

## 7. 分析阶段设计

### 7.1 数据查询

抽取完成后，结果 CSV 作为会话工件保留。Agent 可通过以下方式分析：

**工具**：
- `query_extracted_data(extraction_id, sql)`：使用 DuckDB 直接对 CSV 执行 SQL。
- `analyze_extracted_data(extraction_id, request)`：Agent 根据用户需求，自行决定生成 SQL 还是 Python 分析脚本。

**DuckDB 示例**：

```sql
SELECT carrier, pol, pod, container_type, MIN(amount) AS min_price
FROM 'data/artifacts/{thread_id}/extractions/{extraction_id}.csv'
WHERE pod = 'LOS ANGELES'
GROUP BY carrier, pol, pod, container_type
ORDER BY min_price ASC
```

### 7.2 多文件对比分析

对于多报价单对比，Agent 可生成跨 CSV 的 SQL JOIN：

```sql
SELECT a.carrier, a.pol, a.pod, a.amount AS price_a, b.amount AS price_b
FROM 'ext-a.csv' AS a
JOIN 'ext-b.csv' AS b
  ON a.pol = b.pol AND a.pod = b.pod AND a.container_type = b.container_type
```

### 7.3 生成式 UI 输出

分析结果通过现有 `render_ui` 工具渲染：

- **表格**：`data_table` 组件；
- **图表**：`chart` 组件（bar / line）；
- **关键指标**：`metric_card` 组件；
- **说明文字**：`markdown_card` 组件。

用户是否保存分析结果到 `reports/` 目录由 Agent 根据用户指令决定（选项 C）。

---

## 8. 前端交互

### 8.1 拖拽上传

在 `CopilotChat` 聊天输入区增加文件拖拽能力：

- 拖拽文件到输入框时触发上传；
- 上传完成后在输入区显示文件卡片（文件名 + 大小）；
- 用户发送消息时，文件 `file_id` 通过 `state.attachments` 或消息 metadata 传给后端。

### 8.2 进度与状态展示

- 文件上传进度条；
- Agent 执行抽取、验证时显示“正在分析…”状态；
- 验证失败时展示验证报告中的异常项，便于用户决定下一步。

### 8.3 UI 组件

复用现有 `catalog` 组件：
- 抽取预览：用 `data_table` 展示前 10 行；
- 验证报告：用 `markdown_card` 或 `data_table` 展示；
- 分析结果：用 `data_table` / `chart` / `metric_card` 组合展示。

---

## 9. 安全与隔离

### 9.1 文件上传安全

- 限制文件类型：仅允许 `.xlsx`, `.xls`（MVP）；
- 限制文件大小：建议最大 20MB；
- 文件名消毒：使用随机 `artifact_id` 作为实际文件名；
- 路径遍历防护：所有文件操作基于 `thread_id` + `artifact_id`，禁止用户传入任意路径。

### 9.2 代码执行安全（MVP）

MVP 采用**受限子进程沙箱**，在开源沙箱选型完成前作为临时方案：

- 白名单 import：仅允许 `pandas`, `openpyxl`, `numpy`, `csv`, `json`, `re` 等数据分析相关库；
- 挂载只读输入目录和只写输出目录；
- 超时限制：默认 60 秒；
- 资源限制：CPU / 内存上限；
- 禁止网络访问；
- 禁止执行 shell 命令；
- 禁止访问环境变量中的敏感信息。

### 9.3 生产沙箱选型（后续）

候选方案：
- **E2B**：开源沙箱，支持 Python/Node，有官方 SDK；
- **Pyodide**：浏览器端 WASM，安全性高但库支持有限；
- **Docker**：隔离性强，部署稍重；
- **Firecracker / gVisor**： heavier，适合大规模多租户。

### 9.4 用户隔离

MVP 阶段先按 `thread_id` 实现会话隔离：所有工件保存在 `data/artifacts/{thread_id}/` 下，所有元数据查询都带 `thread_id` 过滤。

严格用户隔离需后续改造：
- 在 `threads` 和 `artifacts` 表中增加 `user_id`；
- 从 CopilotKit `forwardedProps` 或后端认证中间件获取 `user_id`；
- 所有工件查询改为 `WHERE user_id = ? AND thread_id = ?`。

当前设计已为 `user_id` 预留扩展空间，MVP 不引入用户体系改动。

---

## 10. 接口契约

### 10.1 文件上传

```http
POST /api/files/upload
Content-Type: multipart/form-data

thread_id: thread-xxx
file: <binary>
```

响应：

```json
{
  "artifact_id": "art-001",
  "thread_id": "thread-xxx",
  "original_name": "quote_msc_aug.xlsx",
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "size_bytes": 204800,
  "stored_path": "data/artifacts/thread-xxx/uploads/art-001-quote_msc_aug.xlsx"
}
```

### 10.2 列出本会话文件

```http
GET /api/files/?thread_id=thread-xxx
```

### 10.3 下载文件

```http
GET /api/files/{artifact_id}
```

---

## 11. 阶段规划

### Phase 0：设计确认

- 确认本设计文档；
- 确认 `user_id` 隔离方案；
- 确认沙箱 MVP 方案。

### Phase 1：文件上传与会话工件

- 实现 `/api/files/upload`；
- 实现 `artifacts` 表；
- 实现 `preview_excel` 工具；
- 前端增加拖拽上传组件。

### Phase 2：三段式抽取 Skill

- 实现 `generate_extraction_code` 工具；
- 实现 `execute_extraction_code` 工具（MVP 子进程沙箱）；
- 实现 `validate_extraction_result` 工具；
- 编写 3 个 SKILL.md；
- 实现 `extraction_tasks` 表。

### Phase 3：分析与生成式 UI

- 接入 DuckDB；
- 实现 `query_extracted_data` 和 `analyze_extracted_data`；
- 支持多文件对比分析；
- 通过 `render_ui` 输出 `data_table` / `chart` / `metric_card`。

### Phase 4：生产沙箱替换

- 调研并选型开源沙箱；
- 替换 `subprocess_sandbox.py` 实现；
- 安全加固与性能测试。

---

## 12. 依赖与风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 当前系统无 `user_id`，严格用户隔离需改造线程层 | 中 | 先按 thread 隔离，与用户确认后再加 user_id |
| MVP 子进程沙箱安全性有限 | 高 | 限制白名单库、禁止网络/Shell/敏感访问，尽快切换到专业沙箱 |
| Excel 格式不统一，Agent 生成脚本可能多次失败 | 中 | 通过 preview_excel 和迭代验证降低失败率 |
| 大文件（>1万行）解析和执行耗时较长 | 低 | 设置超时、异步执行、后续可分页处理 |
| DuckDB 并发访问 CSV 文件可能产生锁问题 | 低 | 每次查询复制到临时文件或使用内存表 |

---

## 13. 已确认决策

| 问题 | 决策 |
|------|------|
| 用户隔离 | MVP 先按 `thread_id` 隔离，后续再引入 `user_id` 严格隔离 |
| MVP 沙箱 | 采用受限子进程 + 白名单库方案，后续替换为专业开源沙箱 |
| 脚本迭代策略 | 验证失败时基于上一次脚本做增量修改 |
| 执行前确认 | MVP 脚本生成后立即执行，不增加“先展示再确认”的交互步骤 |
