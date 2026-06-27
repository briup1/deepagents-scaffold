# 英文注释/文档字符串中文化设计文档

## 目标

将 `src/scaffold/` 目录下所有 Python 文件中的英文注释与 docstring 翻译为中文，保持代码逻辑、字符串字面量、日志模板、配置 key、API 路径及标识符不变。

## 范围

- **包含**：`src/scaffold/` 下所有 `.py` 文件中的：
  - 单行注释（`# ...`）
  - 多行注释/块注释
  - 函数、类、模块级 docstring（`"""..."""`）
- **不包含**：
  - `tests/` 目录
  - 代码逻辑、变量名、函数签名
  - 字符串字面量（含日志消息、异常消息、默认提示词）
  - 配置字段名、模型字段 `description`（属于 schema 的一部分）
  - 第三方库代码（`src/.venv` 等）

## 方法

采用**方案 B：子代理并行翻译**。

### 分工

按源码子目录将文件拆分为 4 组，每组由一个子代理独立处理：

1. **代理 A**：`src/scaffold/core/`（agents.py、skills.py、subagents.py、tools.py、__init__.py）
2. **代理 B**：`src/scaffold/api/`（含 routers/、middleware/、deps.py、app.py）
3. **代理 C**：`src/scaffold/infra/config/`、`src/scaffold/infra/middleware/`、`src/scaffold/infra/models/`
4. **代理 D**：`src/scaffold/infra/prompts/`、`src/scaffold/infra/channels/`、`src/scaffold/infra/memory/`、`src/scaffold/infra/logging/`、`src/scaffold/runtime/`、`src/scaffold/plugins/`

### 翻译规则

1. 只翻译注释和 docstring，不改动代码。
2. 技术术语可保留原文或直译后加括号备注，例如 `CompiledStateGraph`、`checkpointer`、`middleware`。
3. 模块级 docstring 需准确概括该模块职责。
4. 函数/类 docstring 的 Args/Returns 等区块标题可保留英文或译为「参数/返回」，但需整组文件保持一致。
5. 不添加 emoji、装饰性分隔线或额外说明。
6. 清理已有的异常/残留字符（例如 `agents.py` 第 137 行的「将」）。

## 验证

所有子代理完成并汇总后，执行：

```bash
ruff format src/scaffold
ruff check src/scaffold
pytest
```

- `ruff format` 修复因翻译导致的换行/缩进问题。
- `ruff check` 保证无语法或 lint 错误。
- `pytest` 保证功能未受影响。

## 风险与规避

| 风险 | 规避措施 |
|---|---|
| 子代理误改字符串字面量 | 在 prompt 中明确禁止；最终由主代理 diff review |
| 多代理编辑同一文件冲突 | 按目录严格拆分，无文件重叠 |
| 翻译后 docstring 过长导致 PEP 8 换行问题 | 用 `ruff format` 自动修正 |
| 术语翻译不一致 | 核心术语列表在 prompt 中给出；必要时保留英文 |

## 关键术语参考

| 英文 | 中文（建议） |
|---|---|
| checkpointer | 检查点器 / checkpointer |
| middleware | 中间件 / middleware |
| backend | 后端 / backend |
| subagent | 子 agent |
| skill | 技能 / skill |
| scaffold | scaffold（保留） |
| harness profile | harness profile |
| CompiledStateGraph | CompiledStateGraph（保留） |
| registry | 注册表 / registry |
| tracing | 链路追踪 / tracing |
