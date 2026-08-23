---
name: extraction-analysis
description: 对抽取结果执行 SQL 查询、自然语言分析、多文件对比，并用生成式 UI 展示
allowed-tools: preview_excel query_extracted_data analyze_extracted_data render_ui
---

# 抽取结果分析与展示

## 触发时机

- 抽取验证通过（`validate_extraction_result` 返回 `passed: true`）后，用户提出分析类问题；
- 典型用户表述：
  - “哪条航线到洛杉矶最便宜？”
  - “按船公司统计一下平均运费”
  - “这份报价单里有多少条记录？”
  - “对比一下这两份报价单的价格”
  - “把结果用表格/图表展示出来”

## 执行步骤

1. **确认数据来源**：使用 `extracted_artifact_id`（抽取验证通过时已展示给用户）作为分析输入。
2. **选择分析方式**：
   - 用户需求明确、可用 SQL 表达 → 调用 `query_extracted_data(extraction_id=..., sql=...)`；
   - 用户给出自然语言需求（最低/平均/分组/计数/对比）→ 调用 `analyze_extracted_data(extraction_id=..., request=..., comparison_extraction_id=可选)`；
   - 涉及两份报价单对比 → 传入 `comparison_extraction_id` 触发跨文件 JOIN。
3. **解读结果**：工具返回 `columns` / `rows` / `row_count`，可能带 `sql`（实际执行的语句）与 `summary`。
4. **渲染展示**：调用 `render_ui` 把结果可视化：
   - 表格：`data_table`（columns 必须为对象数组 `[{key, label}]`，rows 必须为对象数组）；
   - 柱状/折线图：`chart`（`kind: "bar" | "line"`，`data: [{label, value}]`）；
   - 关键指标：`metric_card`（`value: number`, `unit`, `change`）；
   - 说明文字：`markdown_card`。
5. **汇报结论**：用自然语言总结分析结论，附上关键数字。

## SQL 使用规范

- 单文件查询时表名为 **`data`**，例如：`SELECT pod, MIN(amount) FROM data GROUP BY pod`；
- 对比模式时表名为 **`data_a`**（主文件）与 **`data_b`**（对比文件）；
- 仅支持只读 `SELECT` / `WITH` 语句，禁止写操作、多条语句；
- 列名必须与抽取结果 CSV 的列名一致（可用 `preview_excel` 或查询返回的 `columns` 确认）；
- 中文列名可直接使用，如 `SELECT 目的港, MIN(海运费) FROM data GROUP BY 目的港`。

## 输出格式示例

```markdown
**分析结果**（共 {row_count} 行）

- 结论：{summary}
- 执行的 SQL：`{sql}`（可选展示）

[render_ui data_table 展示结果]
```

## 注意事项

- 工具返回 `error` 时（非法 SQL、工件不存在、跨会话访问被拒），把可读错误转达用户，不要假装成功；
- 分析只针对当前会话的抽取结果，不得访问其他会话的工件；
- 大结果集会被 `limit` 截断，向用户说明已截断；
- 结果行过多时优先用聚合 SQL（GROUP BY / MIN / AVG）而不是全表导出。
