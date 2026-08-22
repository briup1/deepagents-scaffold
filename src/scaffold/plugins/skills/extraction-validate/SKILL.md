---
name: extraction-validate
description: 验证抽取结果是否符合目标
---

# Excel 抽取结果验证

## 触发时机

- `execute_extraction_code` 成功返回后，状态为 `validating`，应立即进入本 Skill。
- 用户说“验证一下结果”、“检查一下对不对”时进入。

## 执行步骤

1. **调用验证工具**：调用 `validate_extraction_result(task_id=...)`。
2. **解读报告**：
   - `passed: true` → 状态变为 `success`，向用户展示摘要和关键指标。
   - `passed: false` → 查看 `checks` 中的失败项和 `suggestion`，决定下一步。
3. **迭代策略**：
   - 字段缺失/类型错误：回到 `extraction-code` Skill，调整 requirements 或重新生成脚本。
   - 示例行不匹配：确认用户提供的示例是否来自原始文件；必要时回到 `extraction-goal` 修正示例。

## 输出格式

验证通过：

```markdown
验证通过 ✅

- 任务 ID：{task_id}
- 摘要：{summary}
- 检查项：{checks 数量} 项全部通过
```

验证失败：

```markdown
验证未通过 ❌

- 摘要：{summary}
- 失败项：
  - {rule}: {details}
- 建议：{suggestion}

是否根据失败项重新生成脚本？
```

## 注意事项

- 验证失败后，优先基于上一次脚本做增量修改，不要每次都新建 task。
- 如果连续两次验证失败且原因相同，应回到 `extraction-goal` 重新审视字段定义和示例行。
- 验证通过的数据仍以 CSV 工件形式保留，可用于后续分析（DuckDB 查询、图表渲染等）。
