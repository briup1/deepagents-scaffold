---
name: extraction-code
description: 生成并执行 Excel 抽取脚本
allowed-tools: generate_extraction_code run_extraction_script
---

# Excel 抽取脚本生成与执行

## 触发时机

本 Skill 通常由 `extraction-goal` 触发，或在用户明确说"执行抽取脚本"、"重新生成脚本"时进入。

## 执行步骤

1. **确认任务状态**：
   - 如果已有 `task_id` 且状态为 `code_generated` 或 `goal_setting`，直接调用 `run_extraction_script(task_id=..., mode="iterate")` 调试执行。
   - 如果没有 `task_id`，先用 `generate_extraction_code(...)` 生成脚本并获取 `task_id`。

2. **迭代调试**：调用 `run_extraction_script(task_id=..., mode="iterate")` 在沙箱中执行脚本。
   - 查看 `stdout`/`stderr`/`exit_code`/`result_preview`/`run_count`。
   - 脚本执行成功 → 根据 `result_preview` 判断结果是否正确。
   - 脚本执行失败 → 从返回的 `stderr`/`stdout` 分析原因，调整 requirements 或重新生成脚本，重复执行（最多 8 次）。

3. **收口执行**：当迭代结果满意时，调用 `run_extraction_script(task_id=..., mode="finalize")` 落盘抽取工件。
   - 收口成功 → 状态变为 `validating`，进入 `extraction-validate`。
   - 收口失败 → 根据错误信息回到迭代阶段或重新生成脚本。

4. **错误处理**：
   - 缺少必要字段：调整 requirements 中对应字段的 `aliases` 或将其 `required` 设为 `false`。
   - 类型转换失败：调整字段类型（如 `number` → `string`），或在 constraints 中说明清洗规则。
   - OpenBLAS / NumPy 初始化失败：不要盲目重试；沙箱已默认限制 BLAS 线程数。若仍失败且日志包含 `Cannot allocate memory`，检查文件及解压后体积，并改用分块处理。
   - 执行超时：检查文件是否过大，或要求用户分片上传。

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

## 关键工具差异

| 工具 | 用途 | 模式 |
|------|------|------|
| `run_extraction_script` | 双模式执行：iterate（调试）/ finalize（收口） | iterate / finalize |
| `generate_extraction_code` | 创建 task + 生成脚本（支持模板复用） | 仅初始化 |

## 注意事项

- 不要直接执行用户传入的任意 Python 代码，始终通过工具生成脚本。
- 同一任务多次迭代时，复用同一个 `task_id`，工具会自动更新 `extraction_tasks` 记录。
- 沙箱仅允许 `pandas`、`openpyxl`、`numpy`、`csv`、`json`、`re` 等白名单库。
- `iterate` 模式最多允许 8 次运行（`MAX_RUN_COUNT=8`），超限返回 error。
- `finalize` 模式不计入 `run_count`，但要求任务当前状态必须为 `code_generated`。
