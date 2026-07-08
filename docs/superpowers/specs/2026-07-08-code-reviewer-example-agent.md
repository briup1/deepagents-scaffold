# 结对代码审查员示例 Agent — 设计文档

> **日期：** 2026-07-08  
> **状态：** 已批准实施  
> **相关计划：** `docs/superpowers/plans/2026-07-08-code-reviewer-example-agent.md`

---

## 1. 背景与动机

DeepAgents 脚手架目前提供了通用运行时（`core/`、`infra/`、`api/`、`runtime/`），但缺少一个具体、可演示的 Agent。没有真实示例，就难以评估脚手架的能力边界。本文档定义一个参考示例 Agent，在不动框架代码的前提下，充分串联脚手架的各个重要模块。

## 2. 目标

构建一个**“结对代码审查员”**示例 Agent，使其能够：

- 读取项目文件
- 运行静态分析（`ruff`）和测试（`pytest`）
- 委派给专门的子 Agent 进行审查、测试和重构
- 生成 patch
- 在用户确认后应用文件修改
- 跨会话记住用户偏好
- 输出结构化的 Markdown 审查报告

该示例必须完全通过 `config.yaml` + 插件 + 技能来组装，不得修改 `core/`、`infra/`、`api/` 或 `runtime/`。

## 3. 范围

### 范围内

- 在 `src/scaffold/plugins/tools/code_review.py` 中新增工具
- 在 `src/scaffold/plugins/skills/code_review/SKILL.md` 中新增技能
- 在 `examples/code-reviewer/sample/` 下新增示例代码
- 在 `tests/plugins/test_code_review_tools.py` 中新增测试
- 更新 `config.yaml`、`pyproject.toml`、`tests/test_api.py`
- 编写示例 README

### 范围外

- 修改脚手架框架代码
- 新增前端组件（复用现有 UI）
- 生产级 Slack/飞书部署（仅保留配置）
- 超出代码审查范围的通用文件系统 Agent

## 4. 非目标

- 这不是一个独立产品，而是脚手架示例。
- 这不是一个从零构建功能的通用编程助手。
- 不得修改脚手架的 `core/`、`infra/`、`api/`、`runtime/` 文件。

## 5. 用户故事

- 作为开发者，我可以在聊天框中输入文件路径，获得 Markdown 审查报告。
- 作为开发者，我可以看到 Agent 读取文件、运行 `ruff`、调用子 Agent。
- 作为开发者，我可以让 Agent 应用 patch，并看到它自动备份原文件。
- 作为开发者，我可以在以后通过替换插件和配置，用同一个脚手架构建完全不同的 Agent。

## 6. 架构与边界

```
脚手架框架（不改动）：
  src/scaffold/core/
  src/scaffold/infra/
  src/scaffold/api/
  src/scaffold/runtime/

示例专属新增内容：
  src/scaffold/plugins/tools/code_review.py
  src/scaffold/plugins/skills/code_review/SKILL.md
  examples/code-reviewer/
  tests/plugins/test_code_review_tools.py
  config.yaml
  pyproject.toml
```

所有业务逻辑都位于插件和配置中，脚手架只负责组装。

## 7. 工具

| 工具 | 作用 |
|---|---|
| `read_file` | 读取文件，支持行偏移和行数限制 |
| `list_files` | 列出路径下的文件和目录 |
| `run_ruff` | 对目标运行 `ruff check` |
| `run_pytest` | 对目标运行 `pytest` |
| `explain_symbol` | 解析 AST，解释函数或类 |
| `generate_patch` | 生成统一 diff |
| `write_file` | 写入或追加文件，自动备份并带安全限制 |

## 8. 安全与权限

- 所有文件路径都基于项目根目录解析，禁止越界。
- `write_file` 禁止写入：
  - `.env`、`config.yaml`
  - 后缀为 `.key`、`.secret`、`.pem`、`.p12` 的文件
  - `src/scaffold/core/`、`src/scaffold/infra/`、`src/scaffold/api/`、`src/scaffold/runtime/`
- 覆盖文件前，`write_file` 会自动创建 `.bak` 备份。
- 默认行为：Agent 生成 patch 后询问用户是否应用；用户明确说“直接改”时，可跳过确认。

## 9. 子 Agent

| 子 Agent | 角色 | 可用工具 |
|---|---|---|
| `reviewer` | 检查 bug、风格和可维护性 | `read_file`、`list_files`、`run_ruff`、`explain_symbol` |
| `tester` | 生成并运行测试 | `read_file`、`run_pytest`、`write_file` |
| `refactorer` | 提出并应用重构建议 | `read_file`、`explain_symbol`、`generate_patch`、`write_file` |

## 10. 技能（SKILL.md）

`src/scaffold/plugins/skills/code_review/SKILL.md` 提供：

- 审查清单（命名、类型注解、异常处理、文档、测试、复杂度、可维护性）
- Markdown 输出模板
- 生成和应用 patch 的指导

## 11. 画像配置

新增一个名为 `code_reviewer` 的 harness 画像，其系统提示词：

- 定义 Agent 为结对代码审查员
- 指示 Agent 在应用 patch 前先询问用户，除非用户明确让直接修改
- 要求使用 Markdown 输出

并将 `default_harness` 设置为 `code_reviewer`。

## 12. 配置变更

`config.yaml` 必须包含：

- 7 个工具定义
- 3 个子 Agent 定义
- `code_reviewer` 画像
- `default_harness: code_reviewer`

`pyproject.toml` 需在 `[project.optional-dependencies] dev` 中加入 `ruff`，保证示例开箱即用。

## 13. 前端 / API

- 复用现有 React/Vite 聊天界面。
- 不需要新增 API 端点，`/api/runs/stream` 已足够。
- Agent 返回的 Markdown 报告直接在聊天窗口中渲染。

## 14. 测试

- 在 `tests/plugins/test_code_review_tools.py` 中为每个工具编写单元测试
- 在 `tests/test_api.py` 中新增集成测试，验证 `/api/tools/` 返回了新工具
- 手动测试：运行 `bash scripts/dev.sh`，审查 `examples/code-reviewer/sample/bad_code.py`

## 15. 验收标准

- [ ] `ruff check src tests` 通过
- [ ] `pytest` 通过
- [ ] `bash scripts/dev.sh` 能正常启动
- [ ] 聊天界面可以审查示例文件并输出 Markdown 报告
- [ ] Agent 可以生成 patch，并在用户确认后应用，同时创建备份
- [ ] 未修改 `core/`、`infra/`、`api/`、`runtime/` 中的任何文件

## 16. 决策记录

| 决策 | 理由 |
|---|---|
| 示例直接合并到根 `config.yaml` | 用户希望开箱即用 |
| 允许 `write_file` 但带安全限制 | 用户希望展示写文件能力，同时防止破坏脚手架 |
| 默认询问后再写 | 在能力与安全之间取得平衡 |
| `core/infra/api/runtime` 默认只读 | 保护脚手架核心不受示例影响 |
