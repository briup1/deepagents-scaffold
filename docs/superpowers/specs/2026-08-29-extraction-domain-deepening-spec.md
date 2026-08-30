# Extraction 域深化：data_query module 与任务状态机收编

- 日期：2026-08-29
- 来源：架构评审 `/tmp/architecture-review-20260829-124105.html` 候选 B1 + B2（Top recommendation）
- 状态：ready-for-agent（seam 已经用户确认：data_query 新 module + 扩展 ExtractionWorkspace，共 2 个 seam）

## Problem Statement

开发者维护 Excel 抽取域（Extraction）时，理解成本高、改动危险：

- "对抽取结果做查询/分析"这件事没有一个模块承载。分析工具直接 import 查询工具的私有函数（`_artifact_csv`、`_load_table`、`_validate_select_only`、`_fetch_result`），临时文件生命周期（创建 → 执行 → 清理）在两个工具里逐行重复，且闭包在 workspace 块内定义、块外执行——读代码的人必须回溯验证闭包不依赖已退出的上下文。
- Extraction Task 的状态机没有载体。状态字面量集中声明，但流转守卫在两个工具里各写一份、状态赋值散在五个位置、"构造失败 ValidationReport + 置 failed + 返回错误响应"的仪式在同文件内复制粘贴两遍。新增一条错误路径时，没有任何编译期或测试保障能拦住"忘了置 failed"。
- 同一个时间戳辅助函数 `_now()` 在六个文件中重复定义。

## Solution

一次"extraction 域深化"重构，让五个工具退化为薄编排：

1. 新建 data_query module：一个小接口收编查询/分析的全部共享机制（工件校验与会话归属检查、临时文件生命周期、表加载、只读 SQL 校验、结果 JSON 安全化）。query 工具只透传 SQL；analyze 工具只做"自然语言 → SQL"（纯函数）。
2. 深化 ExtractionWorkspace：新增任务流转与失败两个方法，把状态守卫、时间戳刷新、ValidationReport 构造、失败响应包装全部收进 seam 之后。工具里的守卫 if 与失败仪式全部删除。
3. 顺手收敛六处重复的 `_now()`。

不改任何对外行为：工具名称、参数、返回结构、SSE 事件、数据库表结构全部不变。

## User Stories

1. 作为后端开发者，我想在不了解 DuckDB 细节的情况下新增一个"对 Extracted CSV 做计算"的工具，以便工具只包含我自己的业务逻辑。
2. 作为后端开发者，我想让"临时 CSV 文件一定被清理"这条保证只在一个模块里实现，以便我不必在每个新工具里抄写 try/finally。
3. 作为后端开发者，我想让 analyze 工具不再 import 兄弟模块的私有函数，以便重构 query 工具时不会意外砸掉 analyze。
4. 作为后端开发者，我想让"跨会话访问他人 Artifact 被拒绝"这条安全规则只有一个实现，以便审计时只需审一处。
5. 作为后端开发者，我想看到任务状态的全部合法流转定义在一个模块里，以便回答"从 code_generated 能走到哪"不需要 grep 三个文件。
6. 作为后端开发者，我想让"任务失败"的响应结构（ValidationReport + status=failed + error dict）由模块统一构造，以便新增错误路径时不可能忘记其中任何一步。
7. 作为后端开发者，我想用非法状态流转调用 transition 时得到一个结构化的错误响应而不是静默通过，以便 bug 在开发期就暴露。
8. 作为 AI 编码助手，我想让"查询引擎"和"状态机"各有唯一归属模块，以便我定位和修改时不误伤调用点。
9. 作为代码评审者，我想让五个抽取工具的代码只剩下各自的业务逻辑，以便评审时聚焦于逻辑而非重复的样板。
10. 作为维护者，我想让时间戳格式化只有一份实现，以便将来改格式时不用找六处。
11. 作为最终用户，我想让抽取、执行、验证、查询、分析的对外行为与重构前完全一致，以便重构对我透明。

## Implementation Decisions

- 新建 **data_query module**（位于 extraction 基础设施内），接口为单个入口：接收 workspace、工件引用列表（artifact_id + 表名）、以及一个"拿到数据库连接后做什么"的回调，返回结构化结果 dict。seam 之后藏：工件存在性与会话归属校验、临时文件创建与清理（finally 保证）、表加载、SELECT-only 校验、结果的 JSON 安全化。
- **query 工具**改为：校验参数 → 调用 data_query，回调内执行用户 SQL。
- **analyze 工具**改为：保留"自然语言/比较意图 → SQL"的纯函数构造器，执行阶段调用同一 data_query 入口。删除对 query 工具的全部私有 import。
- **ExtractionWorkspace 新增两个方法**：
  - `transition_task`：声明期望的前置状态集合与目标状态；守卫失败时返回结构化 error dict（与现有工具错误响应同构），成功时刷新时间戳并持久化。
  - `fail_task`：接收规则名、细节、建议，构造 ValidationReport、置 failed、持久化并返回工具错误响应。
- 三个工具（generate / execute / validate）中的状态守卫 if、内联 `task.status = ...` 赋值、失败仪式全部替换为上述两个方法调用。
- `_now()` 只保留一份实现，其余五处改为引用。
- 分层纪律不变：工具（plugins）→ workspace（infra）→ repository（infra）；不引入对 core / api 的依赖。
- 尊重 ADR-0001：沙箱相关代码不在本次范围内。

## Testing Decisions

好测试的标准：只测模块接口上的外部行为，不测内部实现细节；调用方与测试穿过同一条 seam。

- **data_query module**：新增专属测试。用临时目录中的真实 CSV + 内存 SQLite workspace，覆盖：正常查询、多工件加载、非法 SQL（非 SELECT）拒绝、跨会话 Artifact 拒绝、CSV 读取失败、SQL 执行失败、临时文件在异常路径下仍被清理。一次测试投入覆盖两个工具共享的全部机制（leverage）。
- **ExtractionWorkspace 状态机**：扩展现有 workspace 测试，用 fake repository 穷尽五个状态 × 合法/非法流转的矩阵，以及 fail_task 的响应结构。
- **SQL 构造器**（analyze 的 NL→SQL）：作为纯函数独立测试，不需要任何基础设施。
- **五个工具**：沿用现有工具级测试（`tests/test_extraction_tasks.py` 及工具相关测试为 prior art），断言对外行为不变；测试中 workspace 以 fake/mock 替换，只验证编排。
- 私有 import 删除后，用 grep 做静态验证：`analyze_extracted_data` 不再出现 `from ... query_extracted_data import`。

## Out of Scope

- 前端任何改动（F1 会话生命周期、F2 附件、F3 catalog 浅壳均另立项）。
- 历史写入策略合并（评审候选 B3 ThreadHistoryRecorder）。
- `$` 引用解析器统一（评审候选 B4）。
- 沙箱替换（ADR-0001 已决策，Demo 阶段保留 SubprocessSandbox）。
- 工具对外行为的任何变化：名称、参数、返回结构、事件流。
- 新增抽取工具。

## Further Notes

- 术语遵循 CONTEXT.md：Artifact、Extraction Task、Extraction Workspace、Extraction Script、Extracted CSV、Validation Report、Session-scoped（thread_id 隔离）。
- 本 spec 只含 seam 级决策，不含文件路径与代码片段——落地时以现有模块布局为准。
- 验收命令：`pytest`（全量）、`ruff check src tests`、以及上述静态 grep 验证。
