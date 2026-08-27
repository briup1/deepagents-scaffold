# Claude Code 使用 GPT-5.6 时过早压缩：原因与解决方案

> 调研日期：2026-08-27
> 适用场景：Claude Code 通过 Anthropic 兼容网关调用 `gpt-5.6` / `gpt-5.6-sol` 等非 Anthropic 模型 ID。

## 结论

最常见根因不是 GPT-5.6 本身上下文很小，而是 **Claude Code 不认识该自定义模型 ID，按 200K 上下文窗口兜底，并主动执行 auto-compact**。

```text
自定义模型 ID（如 gpt-5.6）
        ↓
Claude Code 无内置窗口元数据
        ↓
默认假定 200K
        ↓
预留输出与安全空间
        ↓
比网关真实上限更早触发自动压缩
```

Claude Code 2.1.223 起会主动约束未知模型的上下文；当前 2.1.247 在本机启动 `gpt-5.6` 时明确提示其为未识别模型，并默认按 200K auto-compact。给进程设置 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000` 后，`/context` 显示 `Auto-compact window: 272k tokens`。

## 官方事实

### 1. 未识别模型默认按 200K

Claude Code 的模型配置文档说明：无法识别上下文窗口的自定义模型 ID 默认按 200K 处理；可通过以下方式纠正：

- 为裸模型 ID 设置 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`；
- 给模型 ID 添加 `[1m]` 后缀，将其声明为 1M；
- 使用 `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1` 恢复等待上游 API 报错的旧行为。

来源：

- <https://code.claude.com/docs/en/model-config>
- <https://code.claude.com/docs/en/env-vars>
- <https://github.com/anthropics/claude-code/issues/68522>

### 2. 当前版本应优先用裸模型 ID + 实际窗口

对于未识别的裸模型 ID，官方文档明确说明 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 会直接生效，同时保留主动压缩保护。这是当前版本最简单、安全的方案。

```bash
export ANTHROPIC_MODEL="gpt-5.6-sol"
export CLAUDE_CODE_MAX_CONTEXT_TOKENS="<网关实际允许的窗口>"
```

如果把模型写成 `gpt-5.6-sol[1m]`，Claude Code 会至少按 1M 处理；要在更小的真实上限前主动压缩，应改用 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`：

```bash
export ANTHROPIC_MODEL="gpt-5.6-sol[1m]"
export CLAUDE_CODE_AUTO_COMPACT_WINDOW="<网关实际允许的窗口>"
```

来源：<https://code.claude.com/docs/en/model-config>

### 3. GPT-5.6 原生 API 窗口不等于代理可用窗口

OpenAI 官方模型页列出的 `gpt-5.6-sol` 上下文窗口为 1,050,000 tokens，最大输出为 128,000 tokens；但 Anthropic 兼容网关可能因订阅路由、协议转换、token 计数和自身限制，只开放其中一部分。因此必须以网关真实上限为准，不能只依据模型名称配置 1.05M。

来源：<https://developers.openai.com/api/docs/models/gpt-5.6-sol>

## 社区方案

### 方案 A：Claudex 的 272K 配置

Claudex 是将 Claude Code Anthropic 请求转换为 OpenAI Codex OAuth 请求的社区代理。其 README 对 GPT-5.6 推荐：

```bash
export ANTHROPIC_DEFAULT_SONNET_MODEL="gpt-5.6-sol[1m]"
export CLAUDE_CODE_AUTO_COMPACT_WINDOW=272000
```

该项目解释：`[1m]` 用于避免 Claude Code 按未知模型默认 200K 截断，`272000` 用于在代理真实限制前主动压缩。

**此数值只代表该代理作者验证的路由，不应直接泛化到其他网关。**

来源：<https://github.com/LeadGrowGTM/claudex>

### 方案 B：使用 Claude 已知模型别名

部分代理把 GPT 模型映射到 `claude-sonnet-*` / `claude-opus-*` 等 Claude Code 已知 ID，以避免未知模型的 200K 兜底及相关能力裁剪。该方式必须同时将 auto-compact 上限固定为代理真实窗口，否则 Claude Code 可能误认为上游拥有完整 1M，最终收到上游 context overflow。

这是社区代理的兼容技巧，不是通用官方配置；优先使用当前官方支持的“裸模型 ID + `CLAUDE_CODE_MAX_CONTEXT_TOKENS`”。

来源：<https://github.com/LeadGrowGTM/claudex>

## 推荐落地顺序

```text
向网关确认 GPT-5.6 实际窗口
        ↓
使用裸模型 ID
        ↓
设置 CLAUDE_CODE_MAX_CONTEXT_TOKENS
        ↓
启动 Claude Code，执行 /context 验证
        ↓
长会话验证不再约 200K 提前压缩
```

### 推荐配置：当前 Claude Code 2.1.247+

在 `~/.claude/settings.json` 的 `env` 中增加：

```json
{
  "env": {
    "ANTHROPIC_MODEL": "gpt-5.6-sol",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "272000"
  }
}
```

其中 `272000` 只是社区代理示例。若网关确认支持完整 OpenAI API 上限，可改为：

```json
{
  "env": {
    "ANTHROPIC_MODEL": "gpt-5.6-sol",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1050000"
  }
}
```

不要在未确认网关能力前直接填 1,050,000。

### 兼容旧代理的配置

仅当代理明确要求 `[1m]` 时使用：

```json
{
  "env": {
    "ANTHROPIC_MODEL": "gpt-5.6-sol[1m]",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "272000"
  }
}
```

## 验证方法

1. 完全退出并重新启动 Claude Code，确保环境变量重新加载。
2. 执行 `/context`。
3. 检查 `Auto-compact window`：
   - 仍为约 200K：配置未加载、变量名错误或模型被其他设置覆盖；
   - 显示配置值：Claude Code 侧已经生效；
   - 未到配置值就被上游拒绝：网关实际窗口更小，需要下调；
   - 到达配置值仍稳定压缩：配置符合预期。
4. 检查实际生效模型，避免 `ANTHROPIC_MODEL`、`ANTHROPIC_DEFAULT_*_MODEL`、`model` 设置及 `/model` 选择互相覆盖。

## 不建议

- **禁用 auto-compact**：只会将提前压缩改成上游 `context overflow`，长任务可能直接失败。
- **无脑添加 `[1m]`**：若代理只支持 200K/272K，最终会由上游拒绝请求。
- **只提高 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`**：只能在同一窗口内推迟少量空间，不能修复模型窗口识别错误。
- **只降低 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`**：可能略微推迟压缩，但会增加长回复被截断的风险。
- **只依赖手工 `/compact`**：属于会话管理手段，不会修正错误的上下文窗口元数据。

## 针对当前机器的核查结果

- Claude Code：`2.1.247`。
- 当前使用自定义 Anthropic 兼容网关；网关模型列表包含 `gpt-5.6-sol` 和 `gpt-5.6-terra`。
- 已将 `~/.claude/settings.json` 的默认模型修改为 `gpt-5.6-sol`，并设置 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000`。
- `/context` 显示 `Auto-compact window: 272k tokens`。
- 最小端到端请求返回 `OK`，实际模型为 `gpt-5.6-sol`，报告的 `contextWindow` 为 `272000`。
