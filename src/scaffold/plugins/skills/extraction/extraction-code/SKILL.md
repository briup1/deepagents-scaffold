---
name: extraction-code
description: 生成并执行 Excel 抽取脚本
allowed-tools: generate_extraction_code execute_extraction_code
---

# Excel 抽取脚本生成与执行

## 触发时机

本 Skill 通常由 `extraction-goal` 触发，或在用户明确说“执行抽取脚本”、“重新生成脚本”时进入。

## 执行步骤

1. **确认任务状态**：
   - 如果已有 `task_id` 且状态为 `code_generated` 或 `goal_setting`，直接调用 `execute_extraction_code(task_id=...)`。
   - 如果没有 `task_id`，先用 `generate_extraction_code(...)` 生成脚本并获取 `task_id`。

2. **执行脚本**：调用 `execute_extraction_code(task_id=...)` 在沙箱中执行脚本。
   - 脚本执行成功 → 状态变为 `validating`，进入 `extraction-validate`。
   - 脚本执行失败 → 从返回的 `stderr` / `stdout` 分析原因，回到本 Skill 重新生成脚本或调整 requirements。

3. **错误处理**：
   - 缺少必要字段：调整 requirements 中对应字段的 `aliases` 或将其 `required` 设为 `false`。
   - 类型转换失败：调整字段类型（如 `number` → `string`），或在 constraints 中说明清洗规则。
   - OpenBLAS / NumPy 初始化失败：不要盲目重试；沙箱已默认限制 BLAS 线程数。若仍失败且日志包含 `Cannot allocate memory`，检查文件及解压后体积，并改用分块处理。
   - 执行超时：检查文件是否过大，或要求用户分片上传。

## 输出格式

```markdown
脚本执行结果：
- 任务 ID：{task_id}
- 输出 CSV 工件 ID：{extracted_artifact_id}
- 行数：{total_rows}
- 列名：{columns}
- 状态：{status}
```

如果失败：

```markdown
脚本执行失败：{error}

失败原因分析：...
建议：...
```

## 注意事项

- 不要直接执行用户传入的任意 Python 代码，始终通过工具生成脚本。
- 同一任务多次迭代时，复用同一个 `task_id`，工具会自动更新 `extraction_tasks` 记录。
- 沙箱仅允许 `pandas`、`openpyxl`、`numpy`、`csv`、`json`、`re` 等白名单库。
