# 领域术语表

本文档记录 `deepagents-scaffold` 项目中与**文件抽取与分析**相关的核心领域术语。仅作词汇定义，不包含实现细节。

## 核心术语

### Artifact / 工件

本会话中产生的所有文件对象，包括原始上传文件、生成的抽取脚本、抽取结果 CSV、分析报告等。每个工件都有唯一的 `artifact_id`。

### Upload File / 上传文件

用户通过聊天框拖拽上传的原始 Excel 文件。上传后成为第一个 Artifact。

### Extraction Task / 抽取任务

一次从原始 Excel 到结构化 CSV 的完整抽取过程。一个任务包含：抽取目标、生成的脚本、抽取结果、验证报告和当前状态。

### Extraction Goal / 抽取目标

用户希望从文件中抽取的内容描述，包括字段名称、字段含义、类型约束、非空要求、示例行等。由 Skill 1 生成并与用户对齐。

### Extraction Script / 抽取脚本

Agent 根据抽取目标生成的 Python 脚本，用于读取原始 Excel 并输出结构化的 CSV 文件。由 Skill 2 负责生成和迭代优化。

### Extracted CSV / 抽取结果

抽取脚本执行后生成的结构化 CSV 文件，作为后续分析、问答、对比的输入。

### Validation Report / 验证报告

Skill 3 对抽取结果进行校验后输出的报告，包含各项检查是否通过、失败原因和改进建议。

### Session-scoped / 会话作用域

所有工件和抽取任务仅对当前 `thread_id` 可见。其他会话无法访问本会话的工件。

### User Isolation / 用户隔离

不同用户之间的工件和数据完全隔离。当前系统通过 `thread_id` 实现初步隔离，未来将通过 `user_id` 实现严格隔离。

### Data Query / 数据查询

对抽取结果 CSV 执行 SQL 或 Python 分析，以回答用户问题或生成报表。

### Generative UI / 生成式 UI

Agent 通过 `render_ui` 工具向前端渲染的交互式组件，包括表格、图表、指标卡等。

## 状态术语

### goal_setting

抽取任务状态：正在 Skill 1 阶段对齐抽取目标。

### code_generated

抽取任务状态：Skill 2 已生成抽取脚本，但尚未执行或验证。

### validating

抽取任务状态：Skill 3 正在对抽取结果进行验证。

### success

抽取任务状态：验证通过，抽取结果可用。

### failed

抽取任务状态：抽取或验证失败，需要人工介入或迭代。
