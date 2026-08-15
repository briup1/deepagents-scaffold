# 日志减负与汉化方案设计文档

**日期**：2026-08-15  
**作者**：Claude Code（AI 协作生成）  
**状态**：待评审  
**关联需求**：`logs/scaffold.log` 当前存在大量重复、英文、低信息密度的中间件 hook 日志，需要减负并汉化，同时保留用户输入、工具调用、记忆系统和中间件生效证据。

---

## 1. 背景与目标

### 1.1 当前问题

一次 `/agent` 请求产生的 23 行日志中，有 14 行（约 61%）是 `scaffold.infra.middleware.telemetry` 输出的 `middleware hook enter/exit` 日志：

```text
middleware hook enter
middleware hook exit
middleware hook enter
middleware hook exit
...
```

这些日志存在以下问题：

- **消息重复**：不同生命周期 hook（`before_agent`、`before_model`、`after_model` 等）使用完全相同的 message 文本，仅在 JSON `extra.hook` 中区分。
- **信息密度低**：记录了“进入/退出”这一机械过程，却没有直接说明中间件是否生效、产生了什么效果。
- **非中文**：本地开发调试时英文日志可读性差。
- **ag-ui 生命周期噪音**：`ag-ui endpoint invoked`、`stream consumer started` 等日志对排查业务问题帮助有限。

### 1.2 设计目标

1. **本地可读**：默认输出中文文本日志，一行一个事件。
2. **减少噪音**：去掉 ag-ui 生命周期细节，只保留用户输入、中间件效果、工具调用、记忆操作。
3. **保留证据**：确保能看到中间件实际生效（如输入护栏阻断、动态上下文注入）。
4. **配置驱动**：通过 `config.yaml` 控制日志级别、格式和类别开关，支持切换回 JSON。
5. **低侵入**：通过日志中间件和 formatter 完成，不侵入 agent/工具/记忆核心业务代码。

---

## 2. 设计原则

- **语义化事件优先**：日志应描述“发生了什么”，而不是“某个函数被调用了”。
- **配置即契约**：`config.yaml` 是日志行为的唯一事实来源，支持热重载。
- **向后兼容**：保留 JSON formatter，生产环境仍可采集结构化日志。
- **可测试**：formatter 和配置解析必须有单元测试；telemetry 事件输出通过 mock logger 断言。

---

## 3. 配置方案

在 `config.yaml` 中新增独立的 `logging` 顶层节点：

```yaml
logging:
  level: info                  # debug | info | warning | error
  format: chinese_text         # json | chinese_text
  categories:
    user_input: true           # 用户输入
    middleware_effect: true    # 中间件实际效果
    tool_call: true            # 工具调用
    memory: true               # 记忆读写
    ag_ui_lifecycle: false     # ag-ui 生命周期（默认关闭）
```

### 3.1 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `level` | string | `info` | 日志级别，控制 handler 阈值。 |
| `format` | string | `chinese_text` | `chinese_text` 为中文文本；`json` 为结构化 JSON。 |
| `categories.user_input` | bool | `true` | 是否记录用户输入摘要。 |
| `categories.middleware_effect` | bool | `true` | 是否记录中间件实际效果。 |
| `categories.tool_call` | bool | `true` | 是否记录工具调用。 |
| `categories.memory` | bool | `true` | 是否记录记忆读写。 |
| `categories.ag_ui_lifecycle` | bool | `false` | 是否记录 ag-ui endpoint/stream 生命周期。 |

### 3.2 热重载

`AppConfig` 已支持基于文件 mtime 的热重载。`configure_logging` 在重载时被重新调用，根据最新配置调整 handler、formatter 和级别。

---

## 4. 日志事件模型

新增 `scaffold.infra.logging.events` 模块，定义统一的日志事件抽象：

```python
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LogCategory(StrEnum):
    USER_INPUT = "user_input"
    MIDDLEWARE_EFFECT = "middleware_effect"
    TOOL_CALL = "tool_call"
    MEMORY = "memory"
    AG_UI_LIFECYCLE = "ag_ui_lifecycle"


@dataclass
class LogEvent:
    category: LogCategory
    message: str
    level: str = "info"
    fields: dict[str, Any] = field(default_factory=dict)
```

事件模型职责：

- 统一不同来源（telemetry、工具、记忆、API）的日志语义。
- 为 formatter 提供标准化的 category/message/fields。
- 便于未来扩展新的日志类别。

---

## 5. 格式化器

### 5.1 ChineseTextFormatter

新增中文文本格式化器，输出形如：

```text
[2026-08-15 14:56:41] [INFO] [middleware_effect] 输入护栏已阻断：pattern=malware_creation action=block | request_id=ca8eb526
```

实现要点：

- 时间戳使用本地时区或 UTC（与现有 JSON formatter 一致）。
- `category` 使用中文类别名或保留英文代码（配置可选）。
- `fields` 按 `key=value` 拼接，字符串过长时截断并加 `...`。
- 敏感字段（如 API key、token、用户隐私数据）必须脱敏，禁止明文输出。

### 5.2 JSONFormatter（保留并增强）

保留现有 JSON formatter，但统一附带 `category` 字段：

```json
{
  "timestamp": "2026-08-15T14:56:41.318105+00:00",
  "level": "INFO",
  "logger": "scaffold.infra.middleware.telemetry",
  "category": "middleware_effect",
  "message": "输入护栏已阻断：pattern=malware_creation action=block",
  "request_id": "ca8eb526-8ddd-43d3-a3c8-d51ca748afd8",
  "pattern": "malware_creation",
  "action": "block"
}
```

### 5.3 Formatter 注册

`configure_logging` 根据 `format` 配置选择 formatter：

```python
if format_type == "chinese_text":
    handler.setFormatter(ChineseTextFormatter())
elif format_type == "json":
    handler.setFormatter(JSONFormatter(indent=json_indent))
```

---

## 6. 各模块改造点

### 6.1 AppConfig（`src/scaffold/infra/config/app_config.py`）

新增 `LoggingConfig` 和 `LogCategoriesConfig` 数据类：

```python
@dataclass
class LogCategoriesConfig:
    user_input: bool = True
    middleware_effect: bool = True
    tool_call: bool = True
    memory: bool = True
    ag_ui_lifecycle: bool = False


@dataclass
class LoggingConfig:
    level: str = "info"
    format: str = "chinese_text"
    categories: LogCategoriesConfig = field(default_factory=LogCategoriesConfig)
```

在 `AppConfig` 中新增 `logging: LoggingConfig` 字段，并在加载/热重载时解析。

### 6.2 日志配置（`src/scaffold/infra/logging/config.py`）

`configure_logging` 改造：

- 接收 `logging_config: LoggingConfig | None = None` 参数。
- 根据 `logging_config.format` 选择 formatter。
- 根据 `logging_config.level` 设置 handler 级别。
- 支持类别过滤（见 6.6）。

### 6.3 日志事件与工具函数（`src/scaffold/infra/logging/events.py`）

新增：

- `LogCategory` 枚举。
- `LogEvent` 数据类。
- `log_event(logger, event)` 辅助函数：根据配置中的类别开关决定是否记录。
- 敏感字段脱敏辅助函数。

### 6.4 Telemetry 中间件（`src/scaffold/infra/middleware/telemetry.py`）

**核心改造**：不再记录机械的 hook enter/exit，改为记录“中间件实际效果”。

#### 改造前

```text
middleware hook enter
middleware hook exit
middleware hook enter
middleware hook exit
...
```

#### 改造后

根据被包装中间件的行为，输出类似：

```text
[middleware_effect] 输入护栏已阻断：pattern=malware_creation action=block
[middleware_effect] 动态上下文已注入：memory_keys=[user_profile] date=2026-08-15
[middleware_effect] 循环检测已触发：tool_name=read_file loop_count=5
[middleware_effect] Token 使用已统计：input_tokens=120 output_tokens=80
```

实现策略：

- 在 `_before_model_impl`、`_after_model_impl` 等 hook 中，比较 state 变化。
- 如果中间件返回了非空 update 或修改了 state，则生成一条 `MIDDLEWARE_EFFECT` 事件。
- 对于 `wrap_model_call`，记录模型调用是否发生、是否被修改、耗时。
- 对于 `wrap_tool_call`，记录工具名和结果状态。
- 保留 `request_id`、`trace_id`、`middleware`、`hook` 等追踪字段，但不再作为主要 message。

### 6.5 API 层（`src/scaffold/api/ag_ui.py`、`src/scaffold/api/app.py`）

#### ag-ui 生命周期日志

将现有 ag-ui 生命周期日志（`endpoint invoked`、`stream consumer started` 等）改为使用 `LogCategory.AG_UI_LIFECYCLE`，默认不记录。

保留一条精简的流式请求完成日志：

```text
[ag_ui_lifecycle] 请求完成：thread_id=xxx run_id=xxx events=76 duration_ms=197
```

#### API 请求日志

将 `Request | POST /agent | 200 | 2.95ms` 汉化并归类为 `user_input`：

```text
[user_input] 用户请求：method=POST path=/agent status=200 duration_ms=2.95
```

同时可选项：在 `user_input` 开启时，记录用户最新消息摘要（角色、内容长度，不记录完整内容）。

### 6.6 类别过滤机制

新增 `CategoryFilter(logging.Filter)`：

```python
class CategoryFilter(logging.Filter):
    def __init__(self, enabled_categories: set[str]):
        self.enabled_categories = enabled_categories

    def filter(self, record: logging.LogRecord) -> bool:
        category = getattr(record, "category", None)
        if category is None:
            return True  # 无 category 的日志默认放行
        return category in self.enabled_categories
```

`configure_logging` 为所有 handler 添加此 filter，根据 `logging.categories` 动态决定放行哪些类别。

### 6.7 工具调用日志（`src/scaffold/core/tools.py` 或工具包装层）

在工具执行前后记录 `LogCategory.TOOL_CALL`：

```text
[tool_call] 工具调用：name=read_file path=src/main.py
[tool_call] 工具返回：name=read_file status=success content_length=512
```

实现方式：

- 在工具注册/发现时，为每个工具添加统一包装器。
- 包装器负责记录调用入参和返回摘要。
- 异常时记录 `status=error` 和错误类型。

### 6.8 记忆系统日志（`src/scaffold/infra/memory/`）

在记忆读写操作时记录 `LogCategory.MEMORY`：

```text
[memory] 记忆读取：keys=[user_profile, todo_list] thread_id=xxx
[memory] 记忆写入：key=todo_list delta_count=1 thread_id=xxx
```

注意：

- 只记录 key/数量/操作类型，不记录完整记忆内容。
- 用户隐私数据必须脱敏。

---

## 7. 迁移计划

### 7.1 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/scaffold/infra/logging/events.py` | 新增 | 日志事件模型、类别枚举、辅助函数。 |
| `src/scaffold/infra/logging/formatters.py` | 新增/拆分 | `ChineseTextFormatter`、`JSONFormatter`、脱敏辅助函数。建议将 formatter 从 `structured.py` 拆出。 |
| `src/scaffold/infra/logging/structured.py` | 修改/可能移除 | 若拆分，则保留兼容导入或删除。 |
| `src/scaffold/infra/logging/config.py` | 修改 | 支持 `LoggingConfig`、类别 filter、formatter 选择。 |
| `src/scaffold/infra/config/app_config.py` | 修改 | 新增 `LoggingConfig` 解析。 |
| `src/scaffold/infra/middleware/telemetry.py` | 修改 | 从 hook enter/exit 改为语义化效果事件。 |
| `src/scaffold/api/ag_ui.py` | 修改 | ag-ui 生命周期日志使用 `AG_UI_LIFECYCLE` 类别。 |
| `src/scaffold/api/app.py` | 修改 | API 请求日志汉化并归类。 |
| `src/scaffold/core/tools.py` | 修改 | 工具调用包装记录 `TOOL_CALL`。 |
| `src/scaffold/infra/memory/` | 修改 | 记忆读写记录 `MEMORY`。 |
| `config.yaml` | 修改 | 新增 `logging` 节点示例。 |
| `tests/infra/logging/test_formatters.py` | 新增/修改 | 覆盖中文文本和 JSON formatter。 |
| `tests/infra/logging/test_events.py` | 新增 | 覆盖事件模型和类别过滤。 |
| `tests/infra/middleware/test_telemetry.py` | 修改 | 断言语义事件，而非 hook enter/exit。 |
| `tests/test_config.py` | 修改 | 覆盖 `LoggingConfig` 解析。 |

### 7.2 向后兼容

- `format: json` 保持现有行为，生产环境无需改动。
- 原有 `text` format 可保留但标记为 deprecated，逐步迁移到 `chinese_text`。
- 未配置 `logging` 节点时，使用新默认值（`chinese_text` + 默认类别开关）。

### 7.3 分阶段实施建议

1. **第一阶段**：事件模型 + formatter + 配置解析 + 类别过滤。
2. **第二阶段**：改造 telemetry 中间件（最大收益）。
3. **第三阶段**：改造 API 层、工具调用、记忆系统日志。
4. **第四阶段**：更新测试、文档、config.yaml 示例。

---

## 8. 测试计划

### 8.1 单元测试

- `test_chinese_text_formatter`：验证时间、级别、类别、消息、字段输出格式；验证长字符串截断；验证敏感字段脱敏。
- `test_json_formatter_category`：验证 JSON 输出包含 `category` 字段。
- `test_category_filter`：验证根据类别开关放行/丢弃日志。
- `test_log_event_helper`：验证 `log_event` 仅在类别开启时调用 logger。

### 8.2 配置测试

- `test_logging_config_defaults`：验证未配置时的默认值。
- `test_logging_config_parsing`：验证完整配置解析。
- `test_logging_config_hot_reload`：验证修改 config.yaml 后日志行为变化。

### 8.3 Telemetry 测试

- `test_telemetry_logs_middleware_effect`：中间件返回 update 时生成 `MIDDLEWARE_EFFECT` 事件。
- `test_telemetry_silent_when_no_effect`：中间件无操作时（如未覆盖的 hook）不生成冗余事件。
- `test_telemetry_wrap_model_call_effect`：验证模型调用包装事件包含正确字段。

### 8.4 集成测试

- 启动服务并调用 `/agent`，检查 `logs/scaffold.log`：
  - 不包含 `middleware hook enter/exit`。
  - 包含中文中间件效果事件。
  - 包含用户输入摘要。
  - ag-ui 生命周期默认不出现。

---

## 9. 风险与回退

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 生产环境依赖 JSON 日志 | 切换 `chinese_text` 后日志采集失败 | 生产保持 `format: json`，仅本地开发用 `chinese_text`。 |
| 类别过滤误删关键日志 | 排障困难 | 默认开启 `middleware_effect`、`tool_call`、`memory`、`user_input`，仅关闭 `ag_ui_lifecycle`。 |
| 敏感信息泄露 | 安全风险 | formatter 和事件辅助函数统一脱敏；增加测试覆盖。 |
| 测试大量失效 | 改造 telemetry 会改断言 | 同步更新 `test_telemetry.py`，并新增 formatter 测试。 |
| 热重载后 formatter 未切换 | 配置不生效 | `configure_logging` 先移除旧 handler 再添加新 handler。 |

---

## 10. 预期效果

改造后，同一次 `/agent` 请求的日志将从 23 行缩减为约 5-8 行，例如：

```text
[2026-08-15 14:56:41] [INFO] [user_input] 用户请求：method=POST path=/agent status=200 duration_ms=2.95 request_id=ca8eb526
[2026-08-15 14:56:41] [INFO] [user_input] 用户消息：role=user content_length=5
[2026-08-15 14:56:41] [WARNING] [middleware_effect] 输入护栏已阻断：pattern=malware_creation action=block request_id=ca8eb526
[2026-08-15 14:56:41] [INFO] [middleware_effect] 动态上下文已注入：memory_keys=[user_profile] date=2026-08-15 request_id=ca8eb526
[2026-08-15 14:56:41] [INFO] [ag_ui_lifecycle] 请求完成：thread_id=thread-xxx run_id=run-xxx events=76 duration_ms=197 request_id=ca8eb526
```

相比原日志，信息密度显著提高，中间件生效证据清晰，且默认不再输出 ag-ui 生命周期噪音。

---

## 11. 待决策事项

1. `ChineseTextFormatter` 中的 `category` 是否显示中文（如 `[中间件效果]`）还是保留英文代码（`[middleware_effect]`）？
2. 用户输入是否需要记录内容前 N 个字符预览，还是仅记录长度？
3. 工具调用参数是否全部记录，还是需要按参数名黑名单脱敏？
4. 是否需要为 `chinese_text` 提供可选的彩色输出（如 ERROR 红色、WARNING 黄色）？

这些问题可在实现计划阶段或代码评审时进一步确认。
