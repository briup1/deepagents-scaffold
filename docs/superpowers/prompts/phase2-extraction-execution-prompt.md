# Phase 2 执行提示词：Excel 报价单三段式抽取 Skill

## 你的角色

你是 `deepagents-scaffold` 项目的后端开发助手，负责实现 Phase 2 的核心能力：**三段式抽取 Skill**（目标对齐 → 代码生成 → 结果验证）。

Phase 1（文件上传、会话工件、`preview_excel`）已完成。你的任务是在现有基础设施上，补全抽取任务的完整链路，使 Agent 能够从 Excel 中自动抽取结构化 CSV，并通过验证确保结果可用。

---

## Phase 2 目标

实现以下三个 Skill 和配套工具，使 Agent 能够独立完成抽取任务：

### Skill 1：设立抽取目标
- 接收用户上传的 Excel 文件（通过 `artifact_id`）和自然语言需求；
- 调用 `preview_excel` 了解文件结构；
- 输出结构化的 `ExtractionGoal`，包含字段定义、约束、示例行；
- 将目标写入 `extraction_tasks` 表，状态为 `goal_setting`。

### Skill 2：生成并执行抽取代码
- 根据 `ExtractionGoal` 生成 Python 抽取脚本；
- 通过 `execute_extraction_code` 在受限子进程沙箱中执行脚本；
- 输出结构化 CSV 到 `data/artifacts/{thread_id}/extractions/`；
- 更新 `extraction_tasks` 状态为 `code_generated` / `validating`。

### Skill 3：验证抽取结果
- 将实际抽取结果与目标中的规则、示例行进行比对；
- 输出 `ValidationReport`；
- 验证通过则状态改为 `success`，否则保留失败原因并建议回到 Skill 2 迭代。

---

## 需要新增/修改的模块

### 后端代码

```
src/scaffold/
├── infra/artifacts/
│   └── repository.py          # 如有需要，扩展按 task_id 查询工件的能力
├── infra/sandbox/
│   ├── __init__.py
│   ├── base.py                # 沙箱抽象接口
│   └── subprocess_sandbox.py  # MVP 受限子进程实现
├── plugins/tools/
│   ├── generate_extraction_code.py
│   ├── execute_extraction_code.py
│   └── validate_extraction_result.py
└── infra/history/
    └── repository.py          # 新增 extraction_tasks 表的 CRUD
```

### 配置

- 在 `config.yaml`、`config.test.yaml`、`config.verify.yaml` 中注册上述 3 个新工具；
- 新增 `duckdb` 依赖用于后续分析阶段（Phase 3）。

### 文档

- 为三个 Skill 分别编写 `src/scaffold/plugins/SKILL.md`；
- 更新 `docs/superpowers/specs/2026-08-22-excel-extraction-analysis-design.md` 中的实现状态；
- 更新 `CONTEXT.md`（如引入新术语）。

---

## 关键约束

1. **会话隔离**：所有文件路径必须基于 `thread_id`，所有数据库查询必须带 `thread_id` 过滤。
2. **沙箱安全**：
   - 白名单 import：`pandas`, `openpyxl`, `numpy`, `csv`, `json`, `re` 等；
   - 禁止网络访问、禁止 shell 执行、禁止写入非输出目录；
   - 默认超时 60 秒，内存限制 512MB。
3. **脚本约定**：
   - 输入路径：`/mnt/input/{artifact_id}.xlsx`（沙箱内只读挂载）；
   - 输出路径：`/mnt/output/{extraction_id}.csv`（沙箱内只写挂载）；
   - 脚本必须是纯 Python，不接受用户直接传入代码执行。
4. **错误处理**：任何失败都必须在 `extraction_tasks.validation_report` 中记录可读错误信息，禁止吞掉异常。
5. **类型完整**：所有 Python 函数必须带类型注解，符合 ruff（line-length=120, py312）。
6. **依赖管理**：新增 Python 包使用 `uv add <package>`，禁止手动编辑 `pyproject.toml`。

---

## 数据表结构

参考设计文档，新增 `extraction_tasks` 表：

```sql
CREATE TABLE extraction_tasks (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    upload_artifact_id TEXT NOT NULL,
    status TEXT NOT NULL,              -- goal_setting | code_generated | validating | success | failed
    requirements TEXT,                 -- JSON 格式的 ExtractionGoal
    script_artifact_id TEXT,
    extracted_artifact_id TEXT,
    validation_report TEXT,            -- JSON 格式的 ValidationReport
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
    FOREIGN KEY (upload_artifact_id) REFERENCES artifacts(artifact_id),
    FOREIGN KEY (script_artifact_id) REFERENCES artifacts(artifact_id),
    FOREIGN KEY (extracted_artifact_id) REFERENCES artifacts(artifact_id)
);
```

请在 `src/scaffold/infra/history/repository.py` 中新增 `ExtractionTaskRepository`。

---

## 工具接口定义

### `generate_extraction_code`

输入：

```json
{
  "upload_artifact_id": "art-xxx",
  "requirements": {
    "description": "...",
    "fields": [...],
    "constraints": [...],
    "expected_samples": [...]
  }
}
```

输出：

```json
{
  "task_id": "ext-xxx",
  "script_artifact_id": "art-yyy",
  "script_content": "...",
  "status": "code_generated"
}
```

### `execute_extraction_code`

输入：

```json
{
  "task_id": "ext-xxx"
}
```

输出：

```json
{
  "task_id": "ext-xxx",
  "extracted_artifact_id": "art-zzz",
  "total_rows": 1234,
  "columns": ["carrier", "pol", "pod", ...],
  "status": "validating"
}
```

### `validate_extraction_result`

输入：

```json
{
  "task_id": "ext-xxx"
}
```

输出：

```json
{
  "task_id": "ext-xxx",
  "passed": true,
  "summary": "5 项检查全部通过",
  "checks": [...],
  "suggestion": "",
  "status": "success"
}
```

---

## 成功标准（Definition of Done）

### 功能标准

1. Agent 能够通过自然语言描述，生成可执行的抽取脚本；
2. 脚本执行后生成结构化的 CSV，保存为 `extractions` 类型 Artifact；
3. 验证工具能够自动检查字段存在性、类型、非空约束和示例行一致性；
4. 验证失败时，`validation_report` 明确说明失败项并给出改进建议；
5. 所有状态正确写入 `extraction_tasks` 表；
6. 多轮迭代时，`extraction_tasks` 中的记录被更新而不是新建（除非用户明确要求新任务）。

### 代码标准

1. 新增代码通过 `ruff check src tests` 和 `ruff format src tests`；
2. 新增工具必须在三个配置文件（`config.yaml` / `config.test.yaml` / `config.verify.yaml`）中注册；
3. 所有新增函数带类型注解；
4. 新增模块单测覆盖率不低于 80%。

### 安全标准

1. 沙箱禁止网络访问、禁止 shell、禁止写入输出目录外；
2. 脚本 import 超出白名单时执行失败并返回明确错误；
3. 所有文件操作基于 `thread_id`，不允许用户传入任意路径。

---

## 验证方式

### 1. 单元测试

新增测试文件并确保通过：

```bash
ruff check src tests && ruff format src tests
pytest tests/test_extraction_sandbox.py tests/test_generate_extraction_code.py tests/test_execute_extraction_code.py tests/test_validate_extraction_result.py -v
```

### 2. 端到端测试

使用 `/home/weilan/Desktop/simple_quote.xlsx` 作为真实输入：

```bash
bash scripts/dev.sh
```

然后在聊天中依次验证：

1. 上传 `simple_quote.xlsx`；
2. 告诉 Agent：“请帮我抽取carrier、pol、pod、container_type、amount字段，amount是数字”；
3. 观察 Agent 是否调用 `generate_extraction_code` → `execute_extraction_code` → `validate_extraction_result`；
4. 验证完成后，CSV 应保存到 `data/artifacts/{thread_id}/extractions/`；
5. `extraction_tasks` 表中对应记录 `status` 为 `success`。

### 3. 失败路径测试

构造一个会让抽取失败的场景（例如要求一个不存在的字段），验证：

- `status` 变为 `failed` 或停留在 `code_generated`；
- `validation_report` 包含可读错误；
- Agent 能够根据报告重新生成脚本并再次尝试。

### 4. 沙箱安全测试

生成一个尝试以下操作的脚本，验证执行失败：

- `import os` 并执行 `os.system(...)`；
- `import requests` 并访问网络；
- 写入 `/tmp/malicious.txt`。

### 5. 隔离性测试

两个不同 `thread_id` 的会话分别创建抽取任务，验证彼此无法访问对方的脚本和 CSV。

---

## 禁止事项

- 禁止直接执行用户传入的任意 Python 代码；
- 禁止在沙箱内访问 `.env`、API Key、数据库连接字符串等敏感信息；
- 禁止在日志中打印文件内容、用户数据或敏感路径；
- 禁止绕过 `ruff check` 提交代码。

---

## 建议的推进顺序

1. 先实现 `SubprocessSandbox` 和基础安全测试；
2. 再实现 `generate_extraction_code` 工具（可先用硬编码 prompt 生成脚本）；
3. 然后实现 `execute_extraction_code`，打通脚本生成 → 执行 → 落盘链路；
4. 最后实现 `validate_extraction_result`，完成三段式闭环；
5. 编写三个 Skill 的 `SKILL.md`，让 Agent 知道何时调用、如何迭代。

---

## 参考文档

- `docs/superpowers/specs/2026-08-22-excel-extraction-analysis-design.md`
- `docs/superpowers/plans/2026-08-22-excel-extraction-phase1-e2e-test-plan.md`
- `CONTEXT.md`
- `src/scaffold/plugins/tools/preview_excel.py`（Phase 1 已实现，作为参考）
- `src/scaffold/infra/artifacts/`（Phase 1 已实现）

---

执行过程中如果遇到设计模糊或需要取舍的地方，先停下来向我确认，不要擅自引入与 spec 不符的抽象。
