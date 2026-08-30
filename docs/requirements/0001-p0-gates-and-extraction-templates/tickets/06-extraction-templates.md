# 工单 06：抽取模板复用

**阻塞**：03 | **对应需求**：R4-1 ~ R4-6 | **设计契约**：design.md 3.5

## 范围

- 新增 `extraction_templates` 表（字段与索引见 design.md 3.5，含 `user_id`）+ `ExtractionTemplateRepository`（强制 user_id 过滤）；并入 `ExtractionWorkspace` 生命周期
- 指纹计算工具函数：复用 `preview_excel` 已返回的 sheet_names/columns，产出 design.md 3.5 定义的指纹 JSON 与 signature（sha256 前 16 位）；匹配规则：signature 完全一致才算候选（保守）
- 新增 5 个工具（全 async + 关键字参数，user_id 取自 `user_id_ctx`）：`save_extraction_template` / `match_extraction_template` / `list_extraction_templates` / `rename_extraction_template` / `delete_extraction_template`，config.yaml 注册
- `plugins/skills/data_extractor/SKILL.md` 流程更新：验证通过后经 button_group 询问保存；上传后先 match；命中→确认→写脚本→走现有 execute/validate 链路；不匹配或复用失败→回退完整六步流程（不伪装成功）

**不含**：前端新组件（沿用 button_group）、沙箱（05）。

## 验收（G/W/T）

- [ ] Given 一次抽取验证通过（task.status=success），When Agent 询问并经用户确认保存，Then 模板落库（含目标 JSON、脚本、指纹、来源文件名、user_id）
- [ ] Given 已存模板，When 上传列名与表结构完全一致的新文件，Then match 返回候选；用户确认后直接复用脚本执行并走验证；从上传到验证通过≤2 次交互（不重复目标对齐）
- [ ] Given 已存模板，When 上传列名不同的文件，Then match 返回 `matched=false` 及原因，Agent 自动回退完整抽取流程
- [ ] Given 复用脚本执行或验证失败，When 任一步失败，Then Agent 明确告知失败原因并回退完整流程，不伪装成功
- [ ] Given alice 有模板，When bob 调 list/match/rename/delete，Then 看不到也操作不到（按未找到处理）
- [ ] Given 改动完成，When 运行 `.venv/bin/ruff check src tests && .venv/bin/pytest`，Then 全部通过（含模板生命周期与隔离测试）
