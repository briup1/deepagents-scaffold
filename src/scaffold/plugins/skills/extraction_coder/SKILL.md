---
name: extraction-coder
description: 编写、执行、迭代 Excel 抽取脚本，结合 run_extraction_script 与 normalize_upload_file
allowed-tools: run_extraction_script normalize_upload_file generate_extraction_code validate_extraction_result
---

# Excel 抽取脚本编码与执行

## 触发时机

- 用户上传 Excel 并表达抽取需求，需编写自定义抽取逻辑时
- 需要对上传文件进行规范化预处理（合并单元格拆分、删除线过滤）时
- 抽取脚本需要迭代调试、多次执行验证时
- 从 `extraction-goal` 或 `extraction-code` 技能委派而来

## 执行步骤

1. **规范化上传文件（可选）**：
   - 调用 `normalize_upload_file(artifact_id=..., sheet_index=..., filter_strikethrough=...)` 
   - 获取 `normalized_artifact_id` 作为后续抽取的输入源
   - 此步骤处理合并单元格、删除线行过滤，产出标准化 Excel

2. **生成抽取脚本**：
   - 调用 `generate_extraction_code(requirements=..., upload_artifact_id=...)` 
   - `upload_artifact_id` 可使用规范化后的工件 ID
   - 获取 `task_id` 用于后续执行

3. **迭代执行脚本（iterate 模式）**：
   - 调用 `run_extraction_script(task_id=..., mode="iterate")`
   - 查看 `stdout`/`stderr`/`exit_code`/`result_preview`/`run_count`
   - 根据执行结果调整 requirements 或脚本，重复执行（最多 8 次）
   - 每次执行自动增加 `run_count`，不持久化工件、不迁移状态

4. **收口执行（finalize 模式）**：
   - 当迭代结果满意时，调用 `run_extraction_script(task_id=..., mode="finalize")`
   - 校验执行成功（exit_code=0、输出 CSV）、落盘 extraction 工件
   - 迁移任务状态 `code_generated` → `validating`
   - 返回 `extracted_artifact_id` 供后续验证/分析使用

5. **验证抽取结果**：
   - 调用 `validate_extraction_result(task_id=...)` 
   - 通过 → 状态变为 `success`，可进入 `extraction-analysis`
   - 失败 → 根据验证报告回到步骤 2 或 3 迭代

## 关键工具差异

| 工具 | 用途 | 模式 |
|------|------|------|
| `run_extraction_script` | 双模式执行：iterate（调试）| finalize（收口） | iterate / finalize |
| `execute_extraction_code` | 单一执行模式，直接落盘并迁移状态 | 仅 finalize 等效 |
| `normalize_upload_file` | 文件预处理：合并单元格拆分、删除线过滤 | 预处理阶段 |

## 输出格式

迭代执行时：
```markdown
脚本执行（iterate 模式，第 {run_count} 次）：
- 任务 ID：{task_id}
- 退出码：{exit_code}
- 标准输出：{stdout[:200]}...
- 标准错误：{stderr[:200]}...
- 输出文件：{output_files}
- 结果预览：{result_preview}
```

收口执行时：
```markdown
脚本收口执行（finalize 模式）：
- 任务 ID：{task_id}
- 退出码：{exit_code}
- 输出 CSV 工件 ID：{extracted_artifact_id}
- 结果预览：{result_preview}
- 状态：{status}
```

## 注意事项

- `run_extraction_script` 的 `iterate` 模式最多允许 8 次运行（`MAX_RUN_COUNT=8`），超限返回 error
- `finalize` 模式不计入 `run_count`，但要求任务当前状态必须为 `code_generated`
- 规范化文件会产出 `normalized` 类型工件，记录 `source_upload_artifact_id` 供追溯
- `normalize_upload_file` 的 `filter_strikethrough` 参数默认读取配置 `normalize.filter_strikethrough_default`（默认 true）
- 沙箱仅允许白名单库：pandas、openpyxl、numpy、csv、json、re、math、datetime 等
- 禁止直接执行用户传入的任意 Python 代码，始终通过工具生成并执行脚本
- 同一任务多次迭代时，复用同一个 `task_id`，工具会自动更新 `extraction_tasks` 记录

## 典型工作流示例

```markdown
用户上传报价单 → normalize_upload_file(artifact_id) → normalized_artifact_id
                → generate_extraction_code(requirements, upload_artifact_id=normalized_artifact_id) → task_id
                → run_extraction_script(task_id, mode="iterate") × N 次调试
                → run_extraction_script(task_id, mode="finalize") → extracted_artifact_id
                → validate_extraction_result(task_id) → 通过/失败迭代
                → extraction-analysis 进行后续分析
```