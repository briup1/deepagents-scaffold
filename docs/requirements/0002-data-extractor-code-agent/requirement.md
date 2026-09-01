# 需求记录：data_extractor 演进为 Code Agent 式复杂抽取能力

| 字段 | 内容 |
|------|------|
| 状态 | 原始需求记录（待设计） |
| 日期 | 2026-09-01 |
| 来源 | 与用户的连续需求对齐对话（含 codegraph 实现追踪） |
| 范围 | data_extractor Agent 的复杂抽取能力改造 |
| 性质 | 本文档只忠实记录原始需求与已确认的方向决策，不含具体设计 |

## 1. 背景

对 data_extractor 现有实现（`config.yaml` + `plugins/tools/` 六工具 + `infra/extraction/`）做完整追踪后，确认现状的抽取链路是：

```
preview_excel → generate_extraction_code → execute_extraction_code → validate_extraction_result
```

其中 `generate_extraction_code` 的"代码生成"实为**固定模板渲染**（`_build_extraction_script` 把结构化 `requirements` 注入一个写死的 pandas 脚本），并非 LLM 自由写代码；整个链路受状态机硬约束（`goal_setting → code_generated → validating → success/failed`）。

该设计对常规列级抽取有效，但存在明确的天花板：**模板只能表达列级抽取（找列 → 类型转换 → 过滤），多 sheet 合并、透视、跨行计算、格式异常的表格均无法表达**。

## 2. 核心需求（用户原意逐条）

### R1 复杂抽取是第一优先目标（最核心）

- 现状"复杂抽取能力为零"的结论是**用户不接受**的，必须改变。
- Agent 必须具备处理复杂抽取的能力：使用 Skill、使用工具，核心目标就是处理复杂抽取。
- 现有"模板渲染器"路线的天花板不是打磨问题，而是**要更换执行范式**。

### R2 Agent 要成为"能亲自写代码"的 Agent（Code Agent 范式）

用户明确要求 data_extractor 更像 Code Agent，其工作形态必须是：

1. **亲自写代码**：由 Agent 自己生成抽取代码（而非固定模板渲染）。
2. **亲自执行代码**：Agent 能够执行自己写的代码。
3. **与用户需求对比**：执行代码之后，拿结果与用户的需求做对比，检查哪些地方没有达到需求。
4. **修改代码迭代**：根据对比发现的差距修改代码，再执行，形成"写 → 执行 → 对比 → 修改"的迭代闭环，直到满足需求。

### R3 模板匹配 / 复用后置

- 只有完成最关键的复杂抽取能力之后，再考虑模板匹配、复用问题。
- 复用在时间上必须排在复杂抽取能力之后，不作为本次改造的前提。

## 3. 已确认的方向决策

- 用户同意 **B 为主、A 为辅** 的落地方向：
  - **B（主）**：定义 `extraction_coder` 子 Agent，在 bwrap 隔离沙箱内自由写代码迭代（DeepAgents 原生 Code Agent 形态）。
  - **A（辅）**：主 data_extractor 自身保留理解需求、澄清、最终验证、可视化交付职责，并视需要补充少量工具回路。
- 主 Agent 与子 Agent 的职责切分：主 Agent 负责目标对齐与验收收口，子 Agent 负责沙箱内"写 → 跑 → 看 → 改"的迭代脏活。
- 脚手架已具备全部基础设施：子 Agent 机制（`core/subagents.py`）、bwrap 隔离沙箱（`infra/sandbox/`）、文件工具模板（`plugins/tools/code_review.py`）、工件系统（`infra/extraction/workspace.py`）。

## 4. 后置事项（本次明确不做 / 推后）

- 模板匹配与模板复用优化（结构相似度匹配等）。
- 数据质量报告、分析意图双轨、人工复核、批量抽取等其余能力点（均排在复杂抽取能力之后）。

## 5. 下一步（待设计阶段展开）

- 复杂抽取的最小闭环设计：子 Agent 定义、沙箱工具集（写脚本 / 执行 / 看结果 / 回看源文件）、需求契约与验收标准传递、状态机适配。
- 以真实复杂抽取场景（如多 sheet 合并 + 跨行计算）作为验收用例。
