---
title: data_extractor 演进为 Code Agent 式复杂抽取
requirement: 0002-data-extractor-code-agent
status: draft
date: 2026-09-01
---

# 方案设计：data_extractor → Code Agent 式复杂抽取

## 1. 需求↔方案映射

| 需求子项 | 方案模块 | 覆盖 |
|---------|---------|------|
| R1 复杂抽取能力（多 sheet、跨行计算、透视、格式异常） | extraction_coder 子 Agent + run_extraction_script 双模式 | ✅ |
| R2 Code Agent 范式（写→跑→对比→改迭代） | extraction-coder 技能 + 工作区文件工具 + 迭代上限机制 | ✅ |
| R3 模板匹配后置 | 不做，仅通过脚本固化沉淀素材 | ✅ |
| US1 用户上传复杂表格能抽取 | extraction_coder 自由代码能力 | ✅ |
| US2 Agent 自动改代码重试 | 技能驱动的迭代工作流（8 轮上限） | ✅ |
| US3 迭代失败有人工介入提示 | 主 Agent 降级流程（模板/询问/失败收尾） | ✅ |
| US4 最终脚本可审计 | 工作区脚本固化 + update_task_script | ✅ |
| US5 常规文件走快路径 | 主 Agent 路由决策（模板命中→快路径） | ✅ |
| US6 格式异常文件可抽取 | normalize_upload_file 预处理工具 | ✅ |
| US7 主 Agent 委派携带完整上下文 | 委派协议（需求契约+验收标准+结构摘要） | ✅ |
| US8 子 Agent 代码不污染主对话 | 子 Agent 隔离执行 | ✅ |
| US9 子 Agent 脚本从工作区固化 | 返回路径+摘要+自评（防截断） | ✅ |
| US10 主 Agent 预处理异常文件 | preview_excel 异常信号 + normalize_upload_file | ✅ |
| US11 子 Agent 用原生文件工具 | DeepAgents write_file/edit_file/read_file/ls | ✅ |
| US12 子 Agent 看完整执行结果 | run_extraction_script 返回 stdout/stderr/预览 | ✅ |
| US13 输入输出路径通过环境变量 | INPUT_FILE/OUTPUT_FILE 环境变量契约 | ✅ |
| US14 子 Agent 有验收标准依据 | 需求契约中携带 expected_samples | ✅ |
| US15 子 Agent 知道何时选型 | extraction-coder 技能"解析方案选型"章节 | ✅ |
| US16 子 Agent 能调用预处理工具 | normalize_upload_file 工具白名单 | ✅ |
| US17 子 Agent 通过脚本内省源文件 | 脚本内读取 INPUT_FILE | ✅ |
| US18 新能力不改变主链路工具 | 仅新增 2 个工具，现有工具链保留 | ✅ |
| US19 只新增 2 个自定义工具 | run_extraction_script + normalize_upload_file | ✅ |
| US20 无 LLM 环境可测试工具契约 | pytest mock 测试 S1/S1b/S2/S3 | ✅ |
| US21 子 Agent 迭代不推进状态机 | 迭代模式不迁移状态 | ✅ |
| US22 预处理脚本独立可测试 | normalize_upload_file 独立工具 | ✅ |
| US23 沙箱隔离执行 | bwrap 隔离沙箱（复用） | ✅ |
| US24 文件读写限定工作区 | allow+deny 最小安全闭包 | ✅ |
| US25 迭代有上限与资源限制 | 8 轮上限 + 沙箱 timeout/memory_limit | ✅ |

## 2. 前后对比

### 2.1 用户视角

**现状（前）**：

```
用户上传复杂表格（多 sheet + 合并单元格）
    ↓
Agent 调用 generate_extraction_code → 固定 pandas 模板渲染
    ↓
execute_extraction_code → 脚本无法处理复杂结构 → 失败
    ↓
Agent 告知用户"无法处理此文件" → 流程终止
```

**设计后**：

```
用户上传复杂表格（多 sheet + 合并单元格）
    ↓
主 Agent 调用 preview_excel → 发现异常信号（合并单元格数 > 0）
    ↓
主 Agent 调用 normalize_upload_file → 产出规范化工件
    ↓
主 Agent 委派 extraction_coder 子 Agent
    ↓
子 Agent 迭代：写代码→执行→看结果→修改（最多 8 轮）
    ↓
主 Agent 收口：固化脚本→执行→验证→交付
```

### 2.2 系统视角

**现状链路**：

```
┌─────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│ preview_    │ →  │ generate_extraction_ │ →  │ execute_extraction_ │
│ excel       │    │ code（模板渲染）      │    │ code（沙箱执行）    │
└─────────────┘    └──────────────────────┘    └─────────────────────┘
                           ↓                            ↓
                   （仅能处理列级抽取）          ┌─────────────────────┐
                                               │ validate_extraction_ │
                                               │ result              │
                                               └─────────────────────┘
```

**设计后链路**（新增节点高亮，复用资产普通样式）：

```
┌─────────────┐    ┌──────────────────────┐
│ preview_    │ →  │ normalize_upload_    │ ← 新增
│ excel（增强）│    │ file（预处理）        │
└─────────────┘    └──────────────────────┘
                           ↓
              ┌────────────────────────┐
              │ 主 Agent 路由决策       │ ← 新增
              └────────────────────────┘
                     ↙          ↘
            快路径              复杂路径
               ↓                   ↓
    ┌──────────────────┐   ┌──────────────────────┐
    │ generate_        │   │ extraction_coder     │ ← 新增
    │ extraction_code  │   │ 子 Agent（迭代）      │
    │ （模板快路径）    │   └──────────────────────┘
    └──────────────────┘            ↓
                           ┌──────────────────────┐
                           │ run_extraction_      │ ← 新增
                           │ script（双模式）      │
                           └──────────────────────┘
                                    ↓
                           ┌──────────────────────┐
                           │ validate_extraction_ │ ← 复用
                           │ result               │
                           └──────────────────────┘
```

## 3. 接口与契约设计

### 3.1 新增工具：run_extraction_script

```python
async def run_extraction_script(
    task_id: str,
    script_path: str | None = None,        # 工作区内脚本路径（默认 script.py）
    mode: Literal["iterate", "finalize"] = "iterate",
    input_file: str | None = None,          # 可切换为预处理产物
    **kwargs: Any,
) -> dict[str, Any]:
    """在沙箱中执行抽取脚本（双模式）。

    通用契约：
    - 接收工作区内脚本路径，在 bwrap 沙箱执行
    - 通过环境变量 INPUT_FILE/OUTPUT_FILE 传递路径
    - 返回 stdout/stderr/exit_code/output_files/preview（前 N 行 + 列名）

    迭代模式（mode="iterate"）：
    - 不迁移任务状态
    - 不落盘 extraction 工件
    - 计入迭代计数（run_count）
    - 达到 8 次后返回错误

    收口模式（mode="finalize"）：
    - 迁移状态 code_generated → validating
    - 落盘 extraction 工件
    - 不计入迭代计数
    """
```

### 3.2 新增工具：normalize_upload_file

```python
async def normalize_upload_file(
    artifact_id: str,
    config: dict[str, Any] | None = None,  # 可覆盖删除线处理策略
    **kwargs: Any,
) -> dict[str, Any]:
    """规范化上传文件（拆分合并单元格、处理删除线等）。

    Args:
        artifact_id: 上传工件 ID
        config: 可选配置
            - strikethrough_action: "filter" | "mark" | "error"（默认 "filter"）

    Returns:
        - normalized_artifact_id: 规范化工件 ID
        - source_upload_artifact_id: 来源上传工件 ID
        - summary: 变更摘要（合并单元格数、删除线处理数等）
    """
```

### 3.3 workspace 新增接口

```python
async def update_task_script(task_id: str, content: bytes) -> bool:
    """更新任务脚本工件（覆盖式）。

    用于子 Agent 最终脚本固化。固化前做 ast.parse 语法校验。
    """
```

### 3.4 extraction_tasks 表 schema 变更

```sql
-- 新增 run_count 字段（迭代计数）
ALTER TABLE extraction_tasks ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0;
```

### 3.5 ArtifactType 扩展

```python
ArtifactType = Literal["upload", "extraction", "script", "normalized"]
# 新增 "normalized" 类型
```

### 3.6 extraction_coder 子 Agent 配置

```yaml
subagent_definitions:
  items:
    - name: extraction_coder
      description: "复杂 Excel 抽取：自由编写和迭代抽取脚本"
      system_prompt: |
        你是一名数据抽取工程师。你的职责是：
        1. 根据需求契约编写抽取脚本
        2. 在沙箱中执行脚本
        3. 对比结果与验收标准
        4. 修改脚本迭代直到满足需求

        工作流：写 → 跑 → 看 → 改（最多 8 轮）
        返回：脚本路径 + 结果摘要 + 自评
      tools: ["run_extraction_script", "normalize_upload_file"]
      skills: ["src/scaffold/plugins/skills/extraction/extraction-coder"]
      permissions:
        - paths: ["<workspace_dir>/**"]
          operations: ["read", "write"]
          mode: "allow"
        - paths: ["/**"]
          operations: ["read", "write"]
          mode: "deny"
      enabled: true
```

### 3.7 extraction-coder 技能文件

```markdown
---
name: extraction-coder
description: 复杂 Excel 抽取的 Code Agent 工作流
allowed-tools: run_extraction_script normalize_upload_file
---

# 复杂抽取 Code Agent 工作流

## 解析方案选型

1. 常规结构化表格 → pandas
2. 需单元格级控制 → openpyxl
3. 结构异常（preview 异常信号非零）→ 先 normalize_upload_file

## 迭代工作流

1. 读取需求契约（requirements JSON）
2. 读取文件结构摘要（columns、sample_rows、异常信号）
3. 编写脚本 → 写入工作区 script.py
4. 调用 run_extraction_script(mode="iterate")
5. 对比结果与验收标准
6. 若不满足，修改脚本，回到步骤 4
7. 若满足或达到 8 轮上限，返回结果

## 返回协议

返回：
- script_path: 最终脚本路径
- result_summary: 结果摘要（行数、列名）
- self_assessment: 自评（是否满足需求）

不返回脚本完整内容（防截断）。
```

### 3.8 data_extractor prompt 路由增强

在 `config.yaml` 的 `data_extractor` profile 的 `system_prompt_suffix` 中增加路由规则：

```markdown
路由规则：
1. preview_excel 返回异常信号（合并单元格数 > 0 或删除线数 > 0）→
   先调用 normalize_upload_file，再委派 extraction_coder
2. 模板命中（match_extraction_template matched=true）→
   走快路径 generate_extraction_code → execute
3. 其他复杂场景 → 委派 extraction_coder
```

### 3.9 非抽取 profile excluded_tools

```yaml
profiles:
  harness:
    - name: coding
      excluded_tools:
        - run_extraction_script
        - normalize_upload_file
    - name: code_reviewer
      excluded_tools:
        - run_extraction_script
        - normalize_upload_file
    - name: default
      excluded_tools:
        - run_extraction_script
        - normalize_upload_file
```

## 4. 历史资产复用分析

| 资产 | 位置 | 复用方式 | 证据 |
|------|------|----------|------|
| bwrap 隔离沙箱 | `infra/sandbox/bwrap_sandbox.py` | 直接复用，run_extraction_script 调用 get_sandbox().run() | 代码已有完整实现，支持 input_dir/output_dir/extra_env |
| ExtractionWorkspace | `infra/extraction/workspace.py` | 直接复用 create_task/get_task/update_task/save_artifact | 已有完整任务与工件生命周期管理 |
| ArtifactStorage | `infra/artifacts/storage.py` | 直接复用，工件读写 | 已有 thread_id 隔离的文件存储 |
| ExtractionTask 模型 | `infra/history/models.py` | 扩展 run_count 字段 | 已有完整 TaskStatus 状态机 |
| SubAgent 配置 | `infra/config/subagent_config.py` | 扩展 permissions 字段 | 已有 name/description/tools/skills 定义 |
| build_subagents | `core/subagents.py` | 扩展 permissions 映射 | 已有工具解析和 SubAgent 构建 |
| preview_excel | `plugins/tools/preview_excel.py` | 增强返回异常信号 | 已有 openpyxl 解析逻辑 |
| 现有工具链 | `plugins/tools/*.py` | 保留不变 | generate/execute/validate/query/analyze 全部保留 |

**从零开发的项**：

| 项 | 理由 |
|----|------|
| run_extraction_script 工具 | 新增能力，双模式执行语义不同于现有 execute_extraction_code |
| normalize_upload_file 工具 | 新增能力，封装 openpyxl 预处理脚本语义 |
| extraction_coder 子 Agent | 新增能力，Code Agent 工作流 |
| extraction-coder 技能文件 | 新增能力，定义解析选型与迭代工作流 |

## 5. 多方案并列

### 方案 A：子 Agent + 两个新工具（推荐）

| 维度 | 评价 |
|------|------|
| 复杂度 | 中等（2 个新工具 + 1 个子 Agent + 1 个技能） |
| 隔离性 | 好（子 Agent 隔离上下文，沙箱隔离执行） |
| 可测试性 | 好（工具契约层可独立测试） |
| 扩展性 | 好（后续可复用子 Agent 机制扩展其他能力） |
| 风险 | 中（permissions 接线需验证 DeepAgents 兼容性） |

### 方案 B：主 Agent 内直接迭代

| 维度 | 评价 |
|------|------|
| 复杂度 | 低（无需子 Agent，仅新增工具） |
| 隔离性 | 差（代码迭代污染主对话上下文） |
| 可测试性 | 中（工具层可测，但状态机复杂） |
| 扩展性 | 差（迭代逻辑与主 Agent 耦合） |
| 风险 | 高（上下文膨胀、状态机混乱） |

### 方案 C：独立微服务

| 维度 | 评价 |
|------|------|
| 复杂度 | 高（需独立部署、API 设计、通信协议） |
| 隔离性 | 最好（进程级隔离） |
| 可测试性 | 好（独立测试） |
| 扩展性 | 好（可独立扩缩容） |
| 风险 | 高（架构变更大、运维成本高） |

**推荐方案 A**：平衡复杂度与能力，复用现有子 Agent 基础设施，隔离性足够，可测试性好。

## 6. 审查结论（附证据）

### 6.1 可行性

| 检查项 | 结论 | 证据 |
|--------|------|------|
| bwrap 沙箱支持 extra_env | ✅ 通过 | `bwrap_sandbox.py:93-94` 遍历 extra_env 设置 --setenv |
| 子 Agent 机制可用 | ✅ 通过 | `core/subagents.py` 已有完整 build_subagents 实现 |
| 工件系统支持 normalized 类型 | ✅ 通过 | `workspace.py:304` artifact_type 为 str，可扩展 |
| 状态机支持 code_generated 保持 | ✅ 通过 | `workspace.py:234` check_task_transition 支持 allowed 参数 |

### 6.2 复用性

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 沙箱执行可复用 | ✅ 通过 | `execute_extraction_code.py:56-67` 已有完整调用模式 |
| 工件读写可复用 | ✅ 通过 | `workspace.py:290-332` save_artifact/read_artifact 已实现 |
| 任务状态机可复用 | ✅ 通过 | `workspace.py:246-260` transition_task 已实现 |

### 6.3 规范性

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 分层依赖合规 | ✅ 通过 | 新工具在 plugins/tools/，调用 infra/extraction/（允许方向） |
| 工具异步签名 | ✅ 通过 | 所有新增工具均为 async def，接受 **kwargs |
| 类型注解完整 | ✅ 通过 | 将按规范添加完整类型注解 |
| ruff 检查通过 | 未执行 | 待实现后验证 |

## 7. 最小验证

### 7.1 风险点

**最悬假设**：DeepAgents 子 Agent 的 permissions 字段是否支持 list[dict] 格式，以及 builder 是否能正确映射为 FilesystemPermission。

### 7.2 验证方法

检查 DeepAgents 源码中 SubAgent 的 permissions 处理逻辑，确认是否支持 dict 格式。

### 7.3 结果与证据

```bash
# 检查 DeepAgents SubAgent 定义
$ python -c "from deepagents.middleware.subagents import SubAgent; import inspect; print(inspect.signature(SubAgent))"
# 预期：确认 SubAgent 是否有 permissions 参数
```

### 7.4 结论

**待验证**：需在实现阶段确认 DeepAgents permissions 接线方式。若不支持 dict 格式，退化为显式声明"子 Agent 原生文件工具不受限 + 受信用户前提"并记录为已知风险。

---

**下一步**：用户批准方案后，按 spec 文档的变更清单分步实现。
