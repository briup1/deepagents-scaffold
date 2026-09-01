# 领域术语表

本文档记录 `deepagents-scaffold` 项目中与**文件抽取与分析**相关的核心领域术语。仅作词汇定义，不包含实现细节。

## 核心术语

### Artifact / 工件

本会话中产生的所有文件对象，包括原始上传文件、生成的抽取脚本、抽取结果 CSV、分析报告等。每个工件都有唯一的 `artifact_id`。

### Upload File / 上传文件

用户通过聊天框拖拽上传的原始 Excel 文件。上传后成为第一个 Artifact。

### Extraction Task / 抽取任务

一次从原始 Excel 到结构化 CSV 的完整抽取过程。一个任务包含：抽取目标、生成的脚本、抽取结果、验证报告和当前状态。

### Extraction Workspace / 抽取工作区

一次抽取任务所需的完整上下文，由 `ExtractionWorkspace` 模块统一封装。它包含抽取任务（Extraction Task）、关联工件（Artifact：上传文件、脚本、抽取结果、验证报告）、数据库连接与文件系统存储的生命周期。工具通过该工作区访问任务与工件，无需关心连接管理或表迁移细节。

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

### User ID / 用户标识

一级数据隔离维度。每个用户拥有独立的 `user_id`，其下所有会话、工件、抽取任务与模板均归属该标识；`thread_id` 退为用户之下的二级维度。

### Extraction Template / 抽取模板

归属于某一用户的可复用抽取资产，内容包含验证通过的 Extraction Goal、对应的 Extraction Script，以及来源文件的 Structure Fingerprint。仅创建者可见可用。

### Structure Fingerprint / 结构指纹

描述上传文件结构特征的签名（sheet 名、列头签名等），用于判断新上传文件是否可复用已有 Extraction Template。匹配方向保守：宁可误判不匹配走完整流程，也不套错模板。

### Normalized Artifact / 规范化工件

经预处理工具（normalize_upload_file）对上传文件清洗后产出的新工件，拆分合并单元格、处理删除线标记等。`artifact_type` 为 `normalized`，元数据记录 `source_upload_artifact_id` 指向来源上传文件；仅当前会话可见，供 preview 与执行输入使用（模板匹配等既有工具仍只接受 upload 类型）。

### Sandbox Provider / 沙箱提供者

Extraction Script 执行环境的实现选型，由配置驱动切换。本地开发默认使用 subprocess；生产隔离的具体实现（容器 / 托管沙箱 / 其他方案）在方案设计阶段确定。

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
