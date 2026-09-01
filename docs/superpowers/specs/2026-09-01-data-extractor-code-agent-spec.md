# Spec：data_extractor 演进为 Code Agent 式复杂抽取（extraction_coder 子 Agent）

- 日期：2026-09-01
- 来源：需求记录 `docs/requirements/0002-data-extractor-code-agent/requirement.md` + 与用户的连续设计对齐（工具收敛、测试 seam、三点兜底均已确认）
- 状态：ready-for-agent
- Seam：S1 工具契约层（run_extraction_script 双模式 + 工作区约定）+ S1b 预处理与选型支撑 + S2 装配层（子 Agent 定义与白名单）+ S3 状态机与单任务
- 修订记录：
  - v2（2026-09-01）：按 spec_review 首轮评审修订（2 阻断 + 7 重要 + 3 建议）
  - v3（2026-09-01）：按 spec_review 二轮评审修订（3 阻断 + 5 重要 + 4 建议）
  - v4（2026-09-01）：按 spec_review 三轮评审修订（3 阻断 + 5 重要 + 5 建议；核心变更：run_extraction_script 引入迭代/收口双模式，统一解决收口状态机断裂、计数自掐、落盘语义三个 blocker；权限改为 allow+deny 最小闭包）
  - v5（2026-09-01）：按 spec_review 四轮评审修订（1 阻断 + 7 重要 + 5 建议；权限规则补 operations 字段与配置编码；修正 timeout 未接线 / 迁移先例 / 静默跳过三处不实论证；工作区目录纳入配置驱动；S2 改为三级验证 seam）

## Problem Statement

data_extractor 当前通过"模板渲染"完成抽取：`generate_extraction_code` 将结构化 requirements 注入一个固定 pandas 脚本模板，再经 `execute_extraction_code` 沙箱执行、`validate_extraction_result` 验证。该范式的抽取能力被锁定在"列级抽取"（找列 → 类型转换 → 过滤），多 sheet 合并、透视、跨行计算、格式异常的表格均无法表达；而这类复杂抽取恰恰是用户的核心需求。用户明确要求：Agent 必须能亲自写代码、执行代码、拿结果与需求对比、修改代码迭代，即 Code Agent 范式。模板匹配与复用被明确后置。

## Solution

从"模板渲染"切换到"子 Agent 自由代码迭代"，B 为主、A 为辅：

1. 新增子 Agent `extraction_coder`：在隔离沙箱内使用 DeepAgents 原生文件工具（write_file / edit_file / read_file / ls，权限限定于抽取工作区）自由编写和修改抽取脚本（pandas / openpyxl / 预处理后解析），通过执行工具 `run_extraction_script` 反复执行（迭代模式），直到自评满足需求契约。
2. 主 data_extractor 保留现有职责（preview_excel 看结构、与用户对齐需求、validate_extraction_result 硬验收、可视化交付），并负责路由决策：常规 / 模板命中走现有快路径；复杂场景委派给 `extraction_coder`，收口时以收口模式执行。
3. 委派协议显式携带：需求契约（requirements JSON）、验收标准、文件结构摘要（含异常信号）、工作区路径约定、返回协议（最终脚本写入工作区固定路径，返回路径 + 结果摘要 + 自评）。
4. 解析方案选型：抽取脚本不局限于 pandas——解析方案由子 Agent 依据文件结构选择（pandas / openpyxl / 先预处理再解析），由独立挂载于子 Agent 的 extraction-coder 技能"解析方案选型"章节指导；上传文件结构异常（合并单元格、删除线等）时，先经预处理工具洗成规范化文件再解析。
5. 三点兜底：① 子 Agent 最终脚本固化为 script 工件（可审计、可复用）；② 迭代轮次上限（8 次，迭代模式持久化计数强制，收口不计入），超限返回失败摘要由主 Agent 接手；③ 不为原生工具加包装层（YAGNI，踩坑再补）。

## User Stories

1. 作为用户，我希望上传"多 sheet 合并、跨行计算"这类复杂表格也能抽出我要的字段，以便抽取能力不再受限于简单列级表格。
2. 作为用户，我希望 Agent 抽取出错时自己改代码重试而不是直接放弃，以便我不需要懂 pandas。
3. 作为用户，我希望迭代多次仍失败时有人工介入提示，以便我知道卡住了，而不是无限等待。
4. 作为用户，我希望最终采用的抽取脚本被保存下来，以便我可以审计它到底按什么规则抽了什么。
5. 作为用户，我希望常规简单文件仍走原来的快速路径，以便大多数场景依旧快、稳、便宜。
6. 作为用户，我希望合并单元格、删除线等异常格式的文件也能被正确抽取，以便我不必先手工清洗文件。
7. 作为主 Agent，我希望委派子 Agent 时携带需求契约、验收标准与文件结构摘要，以便子 Agent 的自评有明确依据。
8. 作为主 Agent，我希望子 Agent 的代码迭代不污染我与用户的对话上下文，以便我始终专注于需求对齐与验收交付。
9. 作为主 Agent，我希望子 Agent 最终脚本能从工作区直接读取固化，以便不被长内容截断影响。
10. 作为主 Agent，我希望委派前能看到异常信号并先规范化文件，以便子 Agent 面对的是可解析的干净文件。
11. 作为子 Agent，我希望用原生 write_file / edit_file 写和改脚本，以便不需要任何定制写代码工具。
12. 作为子 Agent，我希望执行脚本时看到完整 stdout/stderr 与结果预览，以便我能准确定位失败原因并判断结果是否符合需求。
13. 作为子 Agent，我希望输入输出路径通过约定环境变量传递，以便我不需要关心文件存储与沙箱映射细节。
14. 作为子 Agent，我希望需求契约中带验收标准，以便我判断"满足需求"时有据可依而非主观自评。
15. 作为子 Agent，我希望知道何时选 pandas / openpyxl / 先预处理，以便选对解析方案而不是只会 pandas。
16. 作为子 Agent，我希望文件结构异常时能调用预处理工具洗文件再解析，以便合并单元格、删除线这类脏文件也能被正确抽取。
17. 作为子 Agent，我希望源文件结构能通过脚本内读取 INPUT_FILE 自省，以便原生文件工具不需要访问工作区之外的源文件。
18. 作为后端开发者，我希望新的复杂抽取能力通过"子 Agent + 技能 + 两个新工具"承载，不改变主链路工具，以便现有快路径行为保持稳定。
19. 作为后端开发者，我希望只新增两个自定义工具（执行 + 预处理）而不是一整套定制工具，以便维护面最小。
20. 作为后端开发者，我希望无 LLM 环境下也能测试工具契约与装配，以便回归测试稳定可跑。
21. 作为后端开发者，我希望子 Agent 迭代期间不推进任务状态机，收口时才迁移，以便自由迭代不被状态流转卡死。
22. 作为后端开发者，我希望预处理脚本可独立封装为工具，以便清洗逻辑与解析逻辑解耦、可单独测试。
23. 作为运维，我希望子 Agent 生成的自由代码仍在隔离沙箱内执行，以便任意代码无法破坏宿主环境。
24. 作为运维，我希望子 Agent 的文件读写被限定在抽取工作区，以便原生工具无法读写工作区之外的宿主文件。
25. 作为运维，我希望迭代有轮次上限与资源限制，以便单次抽取的算力成本可预测、可封顶。

## Implementation Decisions

1. **新增子 Agent `extraction_coder`**：通过现有子 Agent 配置机制（subagent_definitions）定义；自定义工具白名单仅含 `run_extraction_script` 与 `normalize_upload_file`（原生文件工具由中间件自动提供，不在白名单内）；挂载独立技能文件 extraction-coder（allowed-tools 与白名单完全一致，见 Decision 7）；继承主 Agent 的 backend 与隔离沙箱；文件工具权限见 Decision 12。
2. **工具注册范围与 profile 隔离**：`run_extraction_script` 与 `normalize_upload_file` 均**全局注册**（config.yaml tools 段）——主 Agent 的 validate_skill_tools 会对全局 skills 校验其声明工具存在，未全局注册会导致子 Agent 装配被静默跳过（build_subagents 对异常为 except + logger.exception + continue，不抛错；漏注册时 extraction_coder 会静默消失）；**故将 extraction_coder 的装配失败改为显式失败（或至少在 S2 覆盖"工具漏注册时装配被拒绝"场景）；**data_extractor 之外的其余 harness profile（default / coding / code_reviewer 等）在 excluded_tools 中排除这两个工具**，避免执行任意脚本的能力扩张到非抽取场景。
3. **执行工具 `run_extraction_script`（迭代 / 收口双模式）**：
   - 通用契约：接收宿主侧工作区内的脚本路径；在隔离沙箱中执行，**通过环境变量 INPUT_FILE / OUTPUT_FILE 向脚本传递输入输出路径（与现有 execute_extraction_code 的契约一致）**，固定路径 /work/in/upload.xlsx 仅作脚本内 fallback；返回完整 stdout/stderr、退出码、输出文件与结果行数，**并附带抽取 CSV 内容预览（前 N 行 + 列名）**；支持指定输入文件（默认任务关联的上传文件，可切换为预处理产物）；复用现有沙箱提供者（bwrap）与超时/内存限制。
   - **迭代模式（子 Agent 使用）**：不迁移任务状态、不落盘 extraction 工件、不计入收口计数（计入迭代计数，见 Decision 10）；输出仅通过返回暴露给子 Agent。
   - **收口模式（主 Agent 使用）**：显式迁移任务状态 code_generated → validating（复用现有 execute 的迁移语义）、落盘 extraction 工件并挂接 task.extracted_artifact_id、不计入迭代计数；供随后 validate_extraction_result 验收。
4. **工作区路径约定（两层，钉死）**：
   - **配置驱动**：新增配置项 `extraction.workspace_dir`（默认 `<project_root>/extraction_workspace`），权限规则与工作区基址均由此单一来源派生；project_root 解析复用现有 SCAFFOLD_PROJECT_ROOT 约定（无则代码目录上级），与 code_review 工具同一常量，避免基址与权限路径漂移。
   - 宿主侧工作区：基址 `workspace_dir/<task_id>/`，包含 `script.py` 与 `output/` 目录；与 DeepAgents backend 的 root_dir 解耦，由 run_extraction_script 与 workspace 模块管理；子 Agent 原生文件工具经 Decision 12 的权限规则限定仅可在此目录读写；任务收尾后工作区保留审计，**保留策略：按 thread 最近 N 个任务（建议 20）清理，量级估算：每任务 ≈ 脚本 + 输出 CSV + 输入副本，通常 <1MB**，清理实现后置。
   - 沙箱侧映射：沿用现有沙箱布局 `/work/in`（只读输入）与 `/work/out`（可写输出），不引入新挂载点；输入文件（上传或预处理产物）映射为 `/work/in/upload.xlsx`，执行输出落盘 `/work/out/extracted.csv`。
   - run_extraction_script 负责宿主 ↔ 沙箱两层互转，并按 Decision 3 契约设置 INPUT_FILE / OUTPUT_FILE 环境变量。
5. **预处理工具 `normalize_upload_file`**：接收上传文件，按封装脚本语义（拆分合并单元格、处理删除线标记等）产出规范化新文件并返回新 artifact；**清洗脚本为内置固定实现（可信代码，宿主执行 openpyxl，不入沙箱），语义清单：合并单元格拆分为区域内所有单元格填充同值；删除线默认过滤该行（config 可覆盖为保留并打标记 / 报错）**；**扩展 ArtifactType Literal 增加 "normalized"**（模型变更），并**放行 preview_excel 对 normalized 工件的预览**（否则规范化文件成为无法预览的死数据）；**明确类型边界：match_extraction_template / generate_extraction_code 等既有工具仍只接受 upload 类型，normalized 仅用于 preview 与执行输入**；规范化工件沿用上传文件的 thread_id 创建，元数据记录 source_upload_artifact_id，仅对当前会话可见；全局注册，主 Agent 与子 Agent 均可调用。
6. **preview_excel 增强**：在现有结构预览基础上增加异常信号（合并单元格数量、删除线单元格数量等），作为主 Agent"是否先预处理"与子 Agent 选型的判断依据；同时放行 normalized 类型工件（见 Decision 5）。
7. **extraction-coder 技能（独立文件，子 Agent 专属目录）**：新建子 Agent 专属技能文件，**放置在子 Agent 专属目录（subagent_definitions items.skills 显式配置路径），不放全局 skills.path，避免主 Agent 的 SkillsMiddleware 也加载它**；frontmatter 的 allowed-tools 仅声明 `run_extraction_script normalize_upload_file`（与子 Agent 白名单完全一致，保证 validate_skill_tools 通过）；内容含"解析方案选型"章节（见下节规则）与迭代工作流指令（写 → 跑 → 读结果 → 对照验收标准 → 修改，每轮修改必须执行并汇报；**源文件结构通过脚本内读取 INPUT_FILE 自省，原生文件工具不访问工作区外文件**）；现有 extraction-code 技能**保持原状**归主 Agent 快路径使用，不改其 allowed-tools。
8. **主 Agent 路由与委派协议（单任务模型）**：主 Agent prompt 增加路由规则（快路径 vs 委派）与预处理决策（preview 异常信号 → 先 normalize_upload_file 再委派）；**整个复杂抽取只建立一个任务**：委派前由主 Agent 调 `generate_extraction_code(requirements=..., upload_artifact_id=...)` 建任务（状态 goal_setting → code_generated），子 Agent 迭代期间状态保持不变，固化与收口在同一任务上完成（见 Decision 9），杜绝悬挂任务；**返回协议（防截断）**：最终脚本写入工作区固定路径，子 Agent 返回"脚本路径 + 结果摘要 + 自评"，不返回脚本完整内容（避免 task 工具消息截断导致固化不完整）；委派 prompt 固定携带需求契约、验收标准、结构摘要（含异常信号）、工作区约定、返回协议。
9. **脚本固化（兜底 ①，单任务）**：**workspace 新增 `update_task_script(task_id, content)` 接口**，主 Agent 从工作区读取子 Agent 最终脚本内容后挂接为任务 #1 的 script 工件（覆盖式），**固化前做 ast.parse 语法校验**，失败则要求子 Agent 重写；固化后在同一任务上收口：run_extraction_script 收口模式（见 Decision 3，输入为上传或规范化文件）→ validate_extraction_result 验收 → success/failed；**不通过 generate_extraction_code(script=...) 二次建任务**（该调用每次都会 create_task，会造成任务 #1 悬挂）；固化产物同时是后续模板复用的素材来源。
10. **迭代上限（兜底 ②，强制）**：`run_extraction_script` 迭代模式按 task_id 累计执行次数，**计数持久化在 extraction_tasks 新增的 run_count 字段**（schema 变更：**本仓库无既有 ALTER TABLE 迁移先例**（现有 _assert_user_id_schema 为缺列抛错拒绝启动，非迁移），故新增 guarded 迁移：PRAGMA table_info 检查缺列后 ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0，配套存量库升级测试——旧库可启动、计数可读写）；达到 8 次后迭代模式返回轮次超限错误并拒绝继续执行（**收口模式不计入，保证"子 Agent 用满配额后主 Agent 仍能收口"**）；超限后子 Agent 返回失败摘要与已尝试方向，由主 Agent 决定降级路径（模板快路径 / 询问用户 / 失败收尾）；**超时兜底说明：subagents.timeout_seconds 当前仅 config 定义、未接线（task 工具调用子 Agent 无超时），本次将其接线为外层等待超时（超时行为与超限共用主 Agent 降级流程）；技能指令要求"每轮修改必须执行并汇报"，原生文件工具循环（不执行脚本）为软约束。**
11. **状态机适配**：子 Agent 迭代模式与迭代全程任务状态**保持不变**（委派前进入的 code_generated 贯穿迭代）；**收口模式显式迁移 code_generated → validating**（复用现有 execute 的迁移语义），随后 validate_extraction_result 按现有守卫（validating / success / failed）正常推进；不修改 validate 守卫。
12. **安全边界（文件工具权限，allow + deny 最小闭包）**：DeepAgents 0.6.8 权限语义为"规则按声明顺序首个匹配生效，无匹配默认 allow"——**仅配置 allow 规则无法拒绝工作区外路径**，因此本次纳入两条规则的最小安全闭包：`[{paths: ["<workspace_dir>/**"], operations: ["read","write"], mode: "allow"}, {paths: ["/**"], operations: ["read","write"], mode: "deny"}]`（**FilesystemPermission 为 dataclass，paths 与 operations 均必填，mode 可选；权限路径必须绝对路径**）；**配置编码：subagent_definitions.permissions 由 list[str] 改为 list[dict]（每条含 paths/operations/mode），builder 映射为 FilesystemPermission 并校验必填字段（现有 builder 需补映射）**；extraction_coder 配置该 permissions（含 subagent_definitions 的 permissions 字段接线到 SubAgent spec，现有 builder 需补映射）；若接线成本过高，退化为显式声明"子 Agent 原生文件工具不受限 + Demo/受信用户场景接受风险"并记录为已知风险（对齐 ADR-0001 受信用户前提，对外开放前必须完成安全审计）。
13. **不加包装层（兜底 ③）**：直接使用 DeepAgents 原生文件工具，不引入 adapter；框架升级踩坑后再评估。
14. **现有工具链保留**：preview_excel（增强）、execute_extraction_code（快路径）、validate_extraction_result、query/analyze、模板工具全部保留；generate_extraction_code 的模板渲染仅保留为快路径能力，不再承担复杂抽取；validate 与 execute 的守卫均不修改。

## Testing Decisions

- **好测试的标准**：只测外部可观察行为（工具输入输出、装配结果、状态迁移、持久化计数），不测 LLM 的内部决策；不依赖真实模型调用。
- **S1 工具契约层（主 seam）**：直接构造上传工件与脚本，断言 `run_extraction_script` 的输入挂载（默认上传文件 / 切换预处理产物）、INPUT_FILE/OUTPUT_FILE 环境变量契约、完整 stderr 返回、**结果预览（前 N 行 + 列名）**、输出落盘与行数报告、超时/内存限制生效、非法脚本的失败行为、**双模式差异（迭代模式不落盘不迁移不计入；收口模式迁移 validating 并挂接 extracted_artifact_id）、第 9 次迭代被拒绝（run_count 持久化计数，测试后重置）且收口模式仍可执行**；工作区约定用 scaffold 的 write_file / read_file（或直接文件 IO，工作区基址位于项目根内以兼容 PROJECT_ROOT 校验）走通"写脚本 → 执行 → 读结果"，不依赖 DeepAgents 原生工具（middleware 注入的工具在 pytest 中不可直接调用）。
- **S1b 预处理与选型支撑**：断言 `normalize_upload_file` 对合并单元格 / 删除线样本的输出符合封装脚本语义、产出新 artifact（artifact_type=normalized、thread_id / source_upload_artifact_id 正确）；断言 preview_excel 增强后能预览 normalized 工件并返回异常信号；断言既有工具（match_extraction_template / generate_extraction_code）对 normalized 仍拒绝（类型边界）；断言扩展后的沙箱 allowed_imports 全量配置下 pandas 与新增模块（pathlib / functools / warnings 等）均可导入（配置为替换语义，须列全量）。
- **S2 装配层**：复用现有 mock 装配模式，断言 `extraction_coder` 出现在子 Agent 构建结果（**装配成功而非静默跳过**）、自定义工具白名单解析为 `[run_extraction_script, normalize_upload_file]`、extraction-coder 技能 allowed-tools 与白名单一致（validate_skill_tools 通过）、**permissions 接线生效（工作区内可读写、工作区外路径被 deny 规则拒绝）**、非抽取 profile 的 excluded_tools 排除了两个新工具、主 Agent 构建产物不含与原生文件工具重名的自定义工具。
- **S3 状态机与单任务**：断言复杂抽取全程只有一个任务（无悬挂双任务）、子 Agent 迭代期间状态保持 code_generated 不变、收口模式迁移 validating 后 validate 按现有守卫正常推进（全链路可走通）。
- **真实 LLM 端到端**：不进 pytest，扩展手动验证脚本覆盖"多 sheet 合并 + 跨行计算 + 脏格式预处理"验收场景。
- **Prior art**：工具契约测试参照现有执行/预览工具测试；装配测试参照现有 acceptance 测试（mock 创建入口捕获参数）；沙箱行为参照现有沙箱测试；预处理测试参照现有上传文件处理测试；schema 迁移测试参照现有 user_id 迁移测试先例。

## 解析方案选型规则（纳入 extraction-coder 技能）

子 Agent 写代码前按以下规则选型：

1. 常规结构化表格（单表头、无合并、无样式语义）→ **pandas**（read_excel 直接读，输入输出路径读 INPUT_FILE/OUTPUT_FILE 环境变量）。
2. 需单元格级控制（合并单元格、样式、删除线、逐 sheet 遍历、定位特定区域）→ **openpyxl**（直接操作单元格/合并区域/样式）。
3. 结构异常（preview 异常信号非零：合并单元格、删除线等）→ **先 normalize_upload_file** 洗成规范化文件，再按 1/2 解析。
4. 预处理语义（删除线是过滤、保留打标记、还是报错）由预处理脚本封装定义，技能不重复实现。

## Out of Scope

- 模板匹配优化与结构相似度匹配（后置，本次仅通过脚本固化沉淀素材）。
- 数据质量报告、分析意图双轨（LLM 生成 SQL）、人工复核 UI、批量抽取。
- 原生文件工具的包装层 / adapter。
- 沙箱提供者扩展（Docker / E2B）与 backend 更换。
- 细粒度文件权限矩阵（按目录/文件的多条规则组合）：本次仅做 allow 工作区 + deny 兜底的最小安全闭包。
- 用户隔离（user_id）与认证相关改动（另有规划）。
- 工作区目录的任务后清理（本次保留审计，清理策略后续迭代）。

## Further Notes

- 本 spec 落实需求记录中的 R1（复杂抽取第一优先）、R2（Code Agent 范式）、R3（复用后置）以及已确认的"B 为主、A 为辅"方向。
- 与 ADR-0001 的关系：ADR 将沙箱升级列为 Demo 后事项，其触发条件包含"需要执行来自公共渠道的 Agent 生成代码"；本次子 Agent 自由代码执行靠近该条件，复用现有 bwrap 沙箱作为强隔离基线，不引入新沙箱提供者。
- 安全边界说明：执行环节由沙箱隔离；文件读写环节由 Decision 12 的 allow+deny 最小闭包收口。若接线成本过高按 ADR-0001 受信用户前提显式接受风险，对外开放前必须完成安全审计。
- 自由代码与沙箱 AST 白名单：allowed_imports 为**替换语义**（配置非空时完全取代默认集），追加 pathlib / functools / warnings 等模块时配置须列全量（含 pandas / openpyxl / numpy / csv / json / re / os / sys / time 等默认集）。
- 成本控制：迭代上限（Decision 10 持久化计数，只计迭代模式）+ 沙箱资源限制共同封顶算力开销；**预算核对**：8 次迭代 ×（LLM 往返 + ≤60s 沙箱执行）最坏接近 900s 的 subagents.timeout_seconds，超时与超限共用主 Agent 降级流程（Decision 10），若实测逼近需下调迭代上限或单次超时。
- 成功任务（需求契约 + 最终脚本）即天然模板素材，模板复用将在复杂能力稳定后作为独立迭代接入。
- 领域词汇：normalized artifact（规范化工件）与 source_upload_artifact_id 已补入 CONTEXT.md 术语表（本版定稿时同步）。

## 变更清单（相对现状实现）

| 变更 | 类型 |
|---|---|
| 新增 `run_extraction_script` 工具（双模式） | 新增 |
| 新增 `normalize_upload_file` 工具 | 新增（封装用户脚本语义） |
| 新增 extraction_coder 子 Agent 定义 + 技能文件 | 新增 |
| subagent_definitions permissions 字段接线到 SubAgent spec | 修改（builder） |
| ArtifactType Literal 增加 "normalized" | 修改（模型） |
| preview_excel 返回异常信号 + 放行 normalized | 修改 |
| extraction_tasks 新增 run_count（ALTER 迁移） | 修改（schema） |
| workspace 新增 update_task_script(task_id, content) | 新增 |
| 全局 allowed_imports 配置列全量白名单 | 修改（config） |
| data_extractor prompt 路由 + 非抽取 profile excluded_tools | 修改（config） |
