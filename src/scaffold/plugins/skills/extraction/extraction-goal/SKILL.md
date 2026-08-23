---
name: extraction-goal
description: 设立 Excel 抽取目标，与用户对齐字段和约束
allowed-tools: preview_excel generate_extraction_code
---

# Excel 抽取目标设立

## 触发时机

当用户上传 Excel 文件并表达抽取需求时，进入本 Skill。典型用户表述：

- “请帮我从这份报价单中抽取 carrier、pol、pod、container_type、amount”
- “把 Excel 里的价格信息导出来”
- “提取第 3 行之后的运价数据”

## 执行步骤

1. **预览文件结构**：调用 `preview_excel(artifact_id=上传工件ID)` 获取 sheet 列表、列名、样本行。
2. **明确需求**：与用户确认要抽取的字段、字段含义、类型、非空约束、示例行、过滤条件。
3. **生成 ExtractionGoal**：构造 JSON 对象，包含：
   - `description`：抽取需求描述
   - `fields`：字段定义数组，每个字段包含 `name`（英文/系统名）、`description`（中文说明）、`type`（`string`/`number`/`integer`/`boolean`/`date`）、`required`（是否非空）、可选 `aliases`（备选列名数组）
   - `constraints`：约束条件数组，如“跳过前 3 行说明文字”
   - `expected_samples`：用户提供的示例行数组（可选）
4. **创建任务**：调用 `generate_extraction_code(upload_artifact_id=..., requirements=...)` 创建抽取任务并生成脚本。
5. **汇报结果**：向用户说明已生成脚本，将自动执行。

## 输出格式

优先用 Markdown 向用户说明：

```markdown
已理解抽取目标：
- 数据源：{artifact_id}
- 字段：{字段列表}
- 约束：{约束列表}

已生成抽取脚本（任务 ID：{task_id}），接下来执行脚本并验证结果。
```

## 注意事项

- 字段名使用英文或拼音，避免特殊字符和空格。
- `required: true` 的字段必须能在文件中找到对应列；若不确定，先设为 `false` 并在验证后迭代。
- 类型声明为 `number` 的字段，脚本会自动清洗 `$`、`¥`、`,` 等字符。
- 如果用户提供示例行，写入 `expected_samples`，验证阶段会检查示例行是否被完整抽取。
