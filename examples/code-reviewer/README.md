# 结对代码审查员示例

本示例展示如何在 DeepAgents 脚手架上组装一个“结对代码审查员”Agent。

## 包含内容

- `sample/bad_code.py`：一段带有常见问题的示例代码。
- `src/scaffold/plugins/tools/code_review.py`：7 个代码审查工具。
- `src/scaffold/plugins/skills/code_review/SKILL.md`：审查清单与输出模板。
- `config.yaml`：工具、子 Agent 与画像配置。

## 快速体验

1. 确保依赖已安装：

   ```bash
   uv pip install -e ".[dev]"
   ```

2. 启动后端和前端：

   ```bash
   bash scripts/dev.sh
   ```

3. 打开前端页面 `http://localhost:3000`，输入：

   ```
   请审查 examples/code-reviewer/sample/bad_code.py
   ```

4. 观察 Agent 读取文件、运行 `ruff`、调用 `reviewer` 子 Agent，并输出 Markdown 审查报告。

## 应用 Patch

Agent 生成 patch 后，默认会询问你是否应用。你可以回复：

- “应用 patch”或“直接改”——Agent 会写入文件并自动创建 `.bak` 备份。
- “再想想”或“不要应用”——Agent 仅保留报告，不修改文件。

## 安全限制

`write_file` 工具禁止写入：

- `.env`、`config.yaml`
- 后缀为 `.key`、`.secret`、`.pem`、`.p12` 的文件
- `src/scaffold/core/`、`src/scaffold/infra/`、`src/scaffold/api/`、`src/scaffold/runtime/`
