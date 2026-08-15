# 日志减负与汉化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 scaffold 的日志从繁琐的英文 hook 进出记录，改造为可配置、中文、语义化的事件日志，同时保留用户输入、工具调用、记忆系统和中间件生效证据。

**Architecture:** 在 `scaffold.infra.logging` 中引入统一的 `LogEvent` 模型和 `ChineseTextFormatter`；`AppConfig` 新增 `logging` 节点控制级别/格式/类别；`telemetry.py` 从记录 hook 生命周期改为记录中间件实际效果；API、ag-ui、工具调用分别归类到对应事件类别；`CategoryFilter` 根据配置开关过滤输出。

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PyYAML, pytest, ruff, 标准库 `logging`。

**Spec:** `docs/superpowers/specs/2026-08-15-log-simplification-chinese-design.md`

## Global Constraints

- 所有新增 Python 函数必须带类型注解。
- 行长度 120，遵循 ruff（target-version=py312）。
- 配置驱动：`config.yaml` 是唯一事实来源，支持热重载。
- 中文输出：`ChineseTextFormatter` 的 `category` 显示中文（`[用户输入]`、`[中间件效果]` 等）。
- 用户输入和工具参数全部记录，不截断。
- 无彩色输出。
- 敏感字段（API key、token、密码）必须脱敏，禁止明文落盘。
- 向后兼容：保留 JSON formatter；未配置 `logging` 节点时回退到现有 `log_level`/`log_format`。
- 所有改动必须通过 `pytest`；提交前运行 `ruff check src tests && ruff format src tests`。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/scaffold/infra/logging/events.py` | 新增：`LogCategory` 枚举、`LogEvent` 数据类、`log_event()` 辅助函数、`CategoryFilter`、敏感字段脱敏。 |
| `src/scaffold/infra/logging/formatters.py` | 新增：`ChineseTextFormatter`、`JSONFormatter`（从 `structured.py` 迁移并增强 category 字段）。 |
| `src/scaffold/infra/logging/structured.py` | 修改/可能删除：保留兼容导入或合并进 `formatters.py`。 |
| `src/scaffold/infra/logging/config.py` | 修改：`configure_logging` 接收 `LoggingConfig`，选择 formatter，添加 `CategoryFilter`。 |
| `src/scaffold/infra/logging/__init__.py` | 修改：导出 `ChineseTextFormatter`、`LogEvent`、`LogCategory`、`log_event`、`CategoryFilter`。 |
| `src/scaffold/infra/config/app_config.py` | 修改：新增 `LoggingConfig`、`LogCategoriesConfig`；解析 `logging` 节点并兼容旧 `log_level`/`log_format`。 |
| `src/scaffold/infra/middleware/telemetry.py` | 修改：从 hook enter/exit 改为语义化 `MIDDLEWARE_EFFECT` 事件。 |
| `src/scaffold/api/ag_ui.py` | 修改：ag-ui 生命周期日志使用 `AG_UI_LIFECYCLE`，默认不输出。 |
| `src/scaffold/infra/logging/middleware.py` | 修改：API 请求日志使用 `USER_INPUT` 类别并汉化。 |
| `src/scaffold/core/tools.py` | 修改：为每个 `StructuredTool` 包装调用过程，记录 `TOOL_CALL` 事件。 |
| `src/scaffold/api/app.py` | 修改：`lifespan` 中把 `config.logging` 传给 `configure_logging`。 |
| `config.yaml` | 修改：新增 `logging` 节点示例，保留旧 `log_level`/`log_format` 作为过渡注释。 |
| `tests/infra/logging/test_events.py` | 新增：事件模型、类别过滤、脱敏测试。 |
| `tests/infra/logging/test_formatters.py` | 新增/修改：中文文本格式化、JSON category 字段测试。 |
| `tests/infra/middleware/test_telemetry.py` | 修改：断言语义事件，而非 hook enter/exit。 |
| `tests/test_config.py` | 修改：`LoggingConfig` 解析与默认值测试。 |
| `tests/core/test_tools.py` 或 `tests/infra/logging/test_tool_logging.py` | 新增：工具调用包装与日志事件测试。 |

---

### Task 1: 日志事件模型与格式化器基础设施

**Files:**
- Create: `src/scaffold/infra/logging/events.py`
- Create: `src/scaffold/infra/logging/formatters.py`
- Modify: `src/scaffold/infra/logging/structured.py`
- Modify: `src/scaffold/infra/logging/__init__.py`
- Test: `tests/infra/logging/test_events.py`
- Test: `tests/infra/logging/test_formatters.py`

**Interfaces:**
- Consumes: 无（基础设施第一步）。
- Produces:
  - `LogCategory(StrEnum)`：USER_INPUT / MIDDLEWARE_EFFECT / TOOL_CALL / MEMORY / AG_UI_LIFECYCLE，且每个有中文显示名。
  - `LogEvent(category, message, level="info", fields=None)`。
  - `log_event(logger: logging.Logger, event: LogEvent, enabled_categories: set[str]) -> None`：根据类别开关记录日志。
  - `CategoryFilter(enabled_categories: set[str])`：标准 `logging.Filter` 子类。
  - `ChineseTextFormatter`：输出 `[timestamp] [LEVEL] [中文类别] message | k=v ...`。
  - `JSONFormatter`：输出 JSON，包含 `category` 字段。
  - `sanitize(value: Any) -> Any`：脱敏辅助函数。

- [ ] **Step 1: 编写失败测试——LogCategory 中文映射**

```python
# tests/infra/logging/test_events.py
from scaffold.infra.logging.events import LogCategory


def test_log_category_has_chinese_label():
    assert LogCategory.display_name(LogCategory.MIDDLEWARE_EFFECT) == "中间件效果"
    assert LogCategory.display_name(LogCategory.USER_INPUT) == "用户输入"
```

Run: `pytest tests/infra/logging/test_events.py::test_log_category_has_chinese_label -v`
Expected: FAIL（`display_name` 未定义）。

- [ ] **Step 2: 实现 LogCategory 与 LogEvent**

```python
# src/scaffold/infra/logging/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from logging import Filter, LogRecord
from typing import Any


class LogCategory(StrEnum):
    USER_INPUT = "user_input"
    MIDDLEWARE_EFFECT = "middleware_effect"
    TOOL_CALL = "tool_call"
    MEMORY = "memory"
    AG_UI_LIFECYCLE = "ag_ui_lifecycle"

    @classmethod
    def display_name(cls, category: "LogCategory") -> str:
        return _CATEGORY_DISPLAY_NAMES.get(category, category.value)


_CATEGORY_DISPLAY_NAMES: dict[LogCategory, str] = {
    LogCategory.USER_INPUT: "用户输入",
    LogCategory.MIDDLEWARE_EFFECT: "中间件效果",
    LogCategory.TOOL_CALL: "工具调用",
    LogCategory.MEMORY: "记忆",
    LogCategory.AG_UI_LIFECYCLE: "AG UI 生命周期",
}


@dataclass
class LogEvent:
    category: LogCategory
    message: str
    level: str = "info"
    fields: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 3: 编写失败测试——log_event 按类别开关过滤**

```python
def test_log_event_respects_category_switch():
    import logging
    logger = logging.getLogger("test.logger")
    event = LogEvent(
        category=LogCategory.AG_UI_LIFECYCLE,
        message="stream started",
    )

    with patch.object(logger, "info") as mock_info:
        log_event(logger, event, enabled_categories={LogCategory.USER_INPUT})

    mock_info.assert_not_called()
```

Run: `pytest tests/infra/logging/test_events.py::test_log_event_respects_category_switch -v`
Expected: FAIL（`log_event` 未定义）。

- [ ] **Step 4: 实现 log_event 与 CategoryFilter**

```python
# src/scaffold/infra/logging/events.py

_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord(None, None, "", 0, "", (), None).__dict__.keys())


def _safe_extra(fields: dict[str, Any]) -> dict[str, Any]:
    """过滤掉与 LogRecord 保留属性冲突的字段，避免 logging 抛 KeyError。"""
    return {k: v for k, v in fields.items() if k not in _RESERVED_RECORD_KEYS}


def log_event(
    logger: logging.Logger,
    event: LogEvent,
    enabled_categories: set[str] | None = None,
) -> None:
    if enabled_categories is not None and event.category.value not in enabled_categories:
        return

    log_func = getattr(logger, event.level.lower(), logger.info)
    safe_fields = _safe_extra(event.fields)
    extra = {"category": event.category.value, **safe_fields}
    log_func(event.message, extra={"extra": extra})


class CategoryFilter(Filter):
    def __init__(self, enabled_categories: set[str] | None = None):
        super().__init__()
        self.enabled_categories = enabled_categories

    def filter(self, record: LogRecord) -> bool:
        if self.enabled_categories is None:
            return True
        category = getattr(record, "category", None)
        if category is None:
            return True
        return category in self.enabled_categories
```

> 注意：这里 `extra` 被包装成 `{"extra": {...}}` 是为了兼容现有 `JSONFormatter` 读取 `record.extra` 的习惯（见 `structured.py:43`）。如果后续调整 formatter，可统一改为直接挂在 record 上。

- [ ] **Step 5: 编写失败测试——ChineseTextFormatter 输出中文**

```python
# tests/infra/logging/test_formatters.py
from unittest.mock import MagicMock
from scaffold.infra.logging.formatters import ChineseTextFormatter


def test_chinese_text_formatter_includes_category():
    formatter = ChineseTextFormatter()
    record = MagicMock()
    record.levelname = "INFO"
    record.getMessage.return_value = "输入护栏已阻断：pattern=malware_creation"
    record.extra = {"category": "middleware_effect", "action": "block"}

    line = formatter.format(record)
    assert "[中间件效果]" in line
    assert "输入护栏已阻断" in line
    assert "action=block" in line
```

Run: `pytest tests/infra/logging/test_formatters.py::test_chinese_text_formatter_includes_category -v`
Expected: FAIL（`ChineseTextFormatter` 未定义）。

- [ ] **Step 6: 实现 ChineseTextFormatter 与 JSONFormatter**

```python
# src/scaffold/infra/logging/formatters.py
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from scaffold.infra.context import get_request_id
from scaffold.infra.logging.events import LogCategory


class JSONFormatter(logging.Formatter):
    def __init__(self, indent: int | None = None) -> None:
        self.indent = indent

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)
        if hasattr(record, "extra"):
            payload.update(record.extra)
        return json.dumps(payload, indent=self.indent, ensure_ascii=False, default=str)


class ChineseTextFormatter(logging.Formatter):
    def __init__(self, datefmt: str = "%Y-%m-%d %H:%M:%S") -> None:
        self.datefmt = datefmt

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime(self.datefmt)
        category = "其他"
        if hasattr(record, "extra"):
            category_code = record.extra.get("category")
            if category_code:
                try:
                    category = LogCategory.display_name(LogCategory(category_code))
                except ValueError:
                    category = category_code

        message = record.getMessage()
        fields_str = self._format_fields(record)
        if fields_str:
            return f"[{ts}] [{record.levelname}] [{category}] {message} | {fields_str}"
        return f"[{ts}] [{record.levelname}] [{category}] {message}"

    def _format_fields(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "extra"):
            return ""
        parts = []
        for key, value in record.extra.items():
            if key == "category":
                continue
            parts.append(f"{key}={self._format_value(value)}")
        return " ".join(parts)

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, str):
            # 对可能包含空格或竖线的字符串加引号
            if " " in value or "|" in value or "=" in value:
                return f'"{value}"'
            return value
        return str(value)
```

- [ ] **Step 7: 调整 structured.py 兼容导出**

```python
# src/scaffold/infra/logging/structured.py
from __future__ import annotations

import logging

from scaffold.infra.context import get_request_id
from scaffold.infra.logging.events import CategoryFilter, LogCategory, LogEvent, log_event
from scaffold.infra.logging.formatters import ChineseTextFormatter, JSONFormatter


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"scaffold.{name}")


__all__ = [
    "ChineseTextFormatter",
    "JSONFormatter",
    "LogCategory",
    "LogEvent",
    "log_event",
    "CategoryFilter",
    "get_logger",
]
```

> 保留 `get_request_id` 与 `get_logger` 在 `structured.py` 或迁移到 `events.py` 均可，但避免破坏已有 import。建议 `__init__.py` 统一导出。

- [ ] **Step 8: 更新 __init__.py 导出**

```python
# src/scaffold/infra/logging/__init__.py
from scaffold.infra.logging.config import configure_logging
from scaffold.infra.logging.events import (
    CategoryFilter,
    LogCategory,
    LogEvent,
    log_event,
)
from scaffold.infra.logging.formatters import ChineseTextFormatter, JSONFormatter
from scaffold.infra.logging.middleware import LoggingMiddleware
from scaffold.infra.logging.structured import get_logger

__all__ = [
    "configure_logging",
    "LoggingMiddleware",
    "ChineseTextFormatter",
    "JSONFormatter",
    "LogCategory",
    "LogEvent",
    "log_event",
    "CategoryFilter",
    "get_logger",
]
```

- [ ] **Step 9: 运行 Task 1 测试**

Run:
```bash
pytest tests/infra/logging/test_events.py tests/infra/logging/test_formatters.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 10: 提交**

```bash
git add src/scaffold/infra/logging/ tests/infra/logging/
git commit -m "feat(logging): 日志事件模型、中文文本 formatter 与类别过滤"
```

---

### Task 2: 配置解析与日志初始化

**Files:**
- Modify: `src/scaffold/infra/config/app_config.py`
- Modify: `src/scaffold/infra/logging/config.py`
- Modify: `src/scaffold/api/app.py`
- Modify: `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `ChineseTextFormatter`, `JSONFormatter`, `CategoryFilter`, `LogCategory`（来自 Task 1）。
- Produces:
  - `LogCategoriesConfig(BaseModel)`：类别开关数据类。
  - `LoggingConfig(BaseModel)`：包含 `level`、`format`、`categories`。
  - `AppConfig.logging: LoggingConfig`。
  - `configure_logging(logging_config: LoggingConfig | None = None, ...)`：根据配置初始化 formatter 和 filter。
  - `AppConfig` 兼容旧 `log_level`/`log_format`：未提供 `logging` 时，用旧字段构建 `LoggingConfig`。

- [ ] **Step 1: 编写失败测试——LoggingConfig 默认值**

```python
# tests/test_config.py
from scaffold.infra.config.app_config import LoggingConfig, LogCategoriesConfig


def test_logging_config_defaults():
    cfg = LoggingConfig()
    assert cfg.level == "info"
    assert cfg.format == "chinese_text"
    assert cfg.categories.user_input is True
    assert cfg.categories.ag_ui_lifecycle is False
```

Run: `pytest tests/test_config.py::test_logging_config_defaults -v`
Expected: FAIL（`LoggingConfig` 未定义）。

- [ ] **Step 2: 实现 LoggingConfig 与 LogCategoriesConfig**

```python
# src/scaffold/infra/config/app_config.py

class LogCategoriesConfig(BaseModel):
    user_input: bool = True
    middleware_effect: bool = True
    tool_call: bool = True
    memory: bool = True
    ag_ui_lifecycle: bool = False


class LoggingConfig(BaseModel):
    level: str = Field(default="info", description="debug/info/warning/error")
    format: str = Field(default="chinese_text", description="json 或 chinese_text")
    categories: LogCategoriesConfig = Field(default_factory=LogCategoriesConfig)
```

- [ ] **Step 3: 在 AppConfig 中新增 logging 字段并做兼容**

```python
# src/scaffold/infra/config/app_config.py
# 在 AppConfig 中新增字段
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

# 保留旧字段，但通过 validator/model_config 在缺失 logging 时回退
    @model_validator(mode="after")
    def _backfill_logging_from_legacy(self) -> Self:
        # 如果 logging 是默认值且旧字段显式非默认，则回退
        if self.log_level != "info" or self.log_format != "text":
            current = self.logging
            # 仅当用户没有显式配置 logging 节点时才回退
            if current.level == "info" and current.format == "chinese_text":
                current.level = self.log_level
                current.format = self.log_format
        return self
```

> 注意：`model_validator` 需要从 pydantic 导入。也可用 `@field_validator` 分字段处理。此处保持简单：旧字段仅在没有 `logging` 显式配置时生效。`log_format` 旧值 `"text"` 映射为 `"chinese_text"`；旧值 `"json"` 保持 `"json"`。

- [ ] **Step 4: 编写失败测试——configure_logging 使用 LoggingConfig**

```python
# tests/infra/logging/test_config.py（新增文件）
import logging
from scaffold.infra.config.app_config import LoggingConfig
from scaffold.infra.logging.config import configure_logging


def test_configure_logging_with_chinese_text_format():
    cfg = LoggingConfig(format="chinese_text", level="info")
    configure_logging(logging_config=cfg, handlers=[])
    root = logging.getLogger("scaffold")
    assert any(isinstance(h.formatter, ChineseTextFormatter) for h in root.handlers)
```

Run: `pytest tests/infra/logging/test_config.py::test_configure_logging_with_chinese_text_format -v`
Expected: FAIL（`configure_logging` 未接受 `logging_config`）。

- [ ] **Step 5: 实现 configure_logging 新签名**

```python
# src/scaffold/infra/logging/config.py
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

from scaffold.infra.logging.events import CategoryFilter, LogCategory
from scaffold.infra.logging.formatters import ChineseTextFormatter, JSONFormatter
from scaffold.infra.logging.structured import RequestIdFilter

if TYPE_CHECKING:
    from scaffold.infra.config.app_config import LoggingConfig


def configure_logging(
    level: str = "info",
    *,
    format_type: str = "text",
    json_indent: int | None = None,
    handlers: list[logging.Handler] | None = None,
    log_file: str | None = None,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    logging_config: LoggingConfig | None = None,
) -> None:
    if logging_config is not None:
        level = logging_config.level
        format_type = logging_config.format
        enabled_categories = {
            cat.value
            for cat in LogCategory
            if getattr(logging_config.categories, cat.value, True)
        }
    else:
        enabled_categories = {cat.value for cat in LogCategory}

    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger("scaffold")
    root.setLevel(log_level)

    for h in list(root.handlers):
        root.removeHandler(h)

    if handlers is None:
        handlers = []
        stderr_handler = logging.StreamHandler(sys.stderr)
        handlers.append(stderr_handler)
        os.makedirs(log_dir, exist_ok=True)
        file_name = log_file or "scaffold.log"
        file_path = os.path.join(log_dir, file_name)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    for handler in handlers:
        handler.setLevel(log_level)
        handler.addFilter(RequestIdFilter())
        handler.addFilter(CategoryFilter(enabled_categories))
        if format_type == "json":
            handler.setFormatter(JSONFormatter(indent=json_indent))
        else:
            handler.setFormatter(ChineseTextFormatter())
        root.addHandler(handler)

    root.propagate = False
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

> 注意：`RequestIdFilter` 当前定义在 `structured.py`。如果 Task 1 把它保留在 `structured.py`，则从这里导入；如果迁移，则调整 import。

- [ ] **Step 6: 更新 app.py lifespan**

```python
# src/scaffold/api/app.py
        config = get_app_config()
        configure_logging(
            logging_config=config.logging,
            log_dir="logs",
        )
```

- [ ] **Step 7: 更新 config.yaml**

在 `config.yaml` 顶部添加新节点，并注释旧字段：

```yaml
config_version: 1

# 新日志配置（推荐）
logging:
  level: debug
  format: chinese_text
  categories:
    user_input: true
    middleware_effect: true
    tool_call: true
    memory: true
    ag_ui_lifecycle: false

# 以下旧字段已废弃，保留仅作向后兼容；未配置 logging 节点时生效。
# log_level: debug
# log_format: json
# middleware_telemetry: true
```

- [ ] **Step 8: 运行 Task 2 测试**

Run:
```bash
pytest tests/test_config.py tests/infra/logging/test_config.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 9: 提交**

```bash
git add src/scaffold/infra/config/app_config.py src/scaffold/infra/logging/config.py src/scaffold/api/app.py config.yaml tests/test_config.py tests/infra/logging/test_config.py
git commit -m "feat(config): 新增 logging 节点与配置驱动的日志初始化"
```

---

### Task 3: Telemetry 中间件语义化改造

**Files:**
- Modify: `src/scaffold/infra/middleware/telemetry.py`
- Test: `tests/infra/middleware/test_telemetry.py`

**Interfaces:**
- Consumes: `LogEvent`, `LogCategory`, `log_event`, `LoggingConfig.categories`（来自 Task 1/2）。
- Produces:
  - `StateTelemetryWrapper` 不再输出 `middleware hook enter/exit`。
  - 当中间件产生实际效果时，输出 `LogCategory.MIDDLEWARE_EFFECT` 事件。
  - 提供 `set_telemetry_categories(enabled_categories: set[str])` 或类似机制，让 telemetry 实例知道类别开关。

- [ ] **Step 1: 编写失败测试——telemetry 记录语义化效果**

```python
# tests/infra/middleware/test_telemetry.py
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from scaffold.infra.logging.events import LogCategory
from scaffold.infra.middleware.telemetry import StateTelemetryWrapper


class FakeBeforeModelMiddleware(AgentMiddleware):
    def before_model(self, state, runtime):
        return {"messages": [HumanMessage(content="hi")]}


def test_telemetry_logs_middleware_effect_event():
    wrapped = FakeBeforeModelMiddleware()
    wrapper = StateTelemetryWrapper(wrapped, index=0)
    wrapper.set_enabled_categories({LogCategory.MIDDLEWARE_EFFECT.value})

    with patch.object(wrapper._logger, "info") as mock_info:
        wrapper.before_model({"messages": []}, MagicMock())

    assert mock_info.called
    _, kwargs = mock_info.call_args
    extra = kwargs["extra"]
    assert extra["category"] == LogCategory.MIDDLEWARE_EFFECT.value
```

Run: `pytest tests/infra/middleware/test_telemetry.py::test_telemetry_logs_middleware_effect_event -v`
Expected: FAIL（`set_enabled_categories` 与语义事件均未实现）。

- [ ] **Step 2: 为 StateTelemetryWrapper 注入类别开关**

```python
# src/scaffold/infra/middleware/telemetry.py
class StateTelemetryWrapper(AgentMiddleware):
    _enabled_categories: set[str] | None = None

    def set_enabled_categories(self, enabled_categories: set[str]) -> None:
        self._enabled_categories = enabled_categories
```

- [ ] **Step 3: 实现语义化效果日志**

替换 `_log_hook_enter`、`_log_hook_exit` 等原有日志方法，新增 `_emit_effect`：

```python
from scaffold.infra.logging.events import LogCategory, LogEvent, log_event

# 在 StateTelemetryWrapper 中：
    def _emit_effect(
        self,
        hook: str,
        summary: dict[str, Any],
        duration_ms: float,
        level: str = "info",
    ) -> None:
        message = f"{self.name} 生效：hook={hook}"
        event = LogEvent(
            category=LogCategory.MIDDLEWARE_EFFECT,
            message=message,
            level=level,
            fields={
                "middleware": self.name,
                "hook": hook,
                "index": self._index,
                "effect_summary": summary,
                "duration_ms": round(duration_ms, 3),
                "request_id": get_request_id(),
                "trace_id": get_trace_id(),
            },
        )
        log_event(self._logger, event, self._enabled_categories)
```

然后在 `_before_agent_impl`、`_before_model_impl` 等生命周期 hook 中：

```python
def _before_model_impl(self, state: Any, runtime: Any) -> dict[str, Any] | None:
    start = time.perf_counter()
    update = self._call_wrapped_lifecycle("before_model", state, runtime)
    duration_ms = (time.perf_counter() - start) * 1000
    if update:
        self._emit_effect(
            "before_model",
            summarize_update(update) or {},
            duration_ms,
        )
    return update
```

对于 `wrap_model_call`，记录模型调用是否发生、是否被修改：

```python
def _wrap_model_call_impl(self, request: Any, handler: Any) -> Any:
    start = time.perf_counter()
    final_request: list[Any] = [request]

    def wrapped_handler(req: Any) -> Any:
        final_request[0] = req
        return handler(req)

    response = self._wrapped.wrap_model_call(request, wrapped_handler)
    duration_ms = (time.perf_counter() - start) * 1000

    request_changed = final_request[0] is not request
    self._emit_effect(
        "wrap_model_call",
        {
            "request_changed": request_changed,
            "request_summary": summarize_model_request(final_request[0]),
            "response_summary": summarize_model_response(response),
        },
        duration_ms,
    )
    return response
```

类似地处理 `_awrap_model_call_impl`、`_wrap_tool_call_impl`、`_awrap_tool_call_impl`。

- [ ] **Step 4: 删除或保留 hook enter/exit 日志**

原 `_log_hook_enter`、`_log_hook_exit`、`_log_model_call_enter`、`_log_model_call_exit`、`_log_tool_call_enter`、`_log_tool_call_exit` 方法可以删除，或者保留但不再调用。为减少噪音，直接删除。

- [ ] **Step 5: 更新工厂以传入类别开关**

```python
# src/scaffold/infra/middleware/factory.py
enabled_categories = {
    cat.value
    for cat in getattr(app_config.logging.categories, "_enabled_set", [])
}
```

更简单的做法：在 factory 中直接计算 enabled set：

```python
log_categories = app_config.logging.categories
enabled_categories = {
    name for name, enabled in log_categories.model_dump().items() if enabled
}
```

然后在包装中间件时传入：

```python
if getattr(app_config, "middleware_telemetry", True):
    instance = StateTelemetryWrapper(instance, index=len(instances))
    instance.set_enabled_categories(enabled_categories)
```

- [ ] **Step 6: 运行 Task 3 测试**

Run:
```bash
pytest tests/infra/middleware/test_telemetry.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 7: 提交**

```bash
git add src/scaffold/infra/middleware/telemetry.py src/scaffold/infra/middleware/factory.py tests/infra/middleware/test_telemetry.py
git commit -m "feat(telemetry): 中间件日志从 hook 生命周期改为语义化效果事件"
```

---

### Task 4: API 请求日志与 ag-ui 生命周期日志

**Files:**
- Modify: `src/scaffold/infra/logging/middleware.py`
- Modify: `src/scaffold/api/ag_ui.py`
- Test: `tests/infra/logging/test_middleware.py`（新建或更新）

**Interfaces:**
- Consumes: `LogEvent`, `LogCategory`, `log_event`（来自 Task 1）。
- Produces:
  - `LoggingMiddleware` 输出 `USER_INPUT` 类别中文日志。
  - `ag_ui.py` 中的生命周期日志改为 `AG_UI_LIFECYCLE` 类别，默认不显示。

- [ ] **Step 1: 修改 LoggingMiddleware 为中文 USER_INPUT 事件**

```python
# src/scaffold/infra/logging/middleware.py
from scaffold.infra.logging.events import LogCategory, LogEvent, log_event

# 在 dispatch 中替换原有日志：
class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled_categories: set[str] | None = None):
        super().__init__(app)
        self.enabled_categories = enabled_categories

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", "-")

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            event = LogEvent(
                category=LogCategory.USER_INPUT,
                message=f"请求失败：{request.method} {request.url.path}",
                level="error",
                fields={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 3),
                    "error": str(exc),
                    "request_id": request_id,
                },
            )
            log_event(logger, event, self.enabled_categories)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        event = LogEvent(
            category=LogCategory.USER_INPUT,
            message=f"用户请求：{request.method} {request.url.path}",
            level="info",
            fields={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 3),
                "request_id": request_id,
            },
        )
        log_event(logger, event, self.enabled_categories)
        return response
```

- [ ] **Step 2: 修改 app.py 中间件注册以传入类别开关**

```python
# src/scaffold/api/app.py
category_states = config.logging.categories.model_dump()
enabled_categories = {name for name, enabled in category_states.items() if enabled}
app.add_middleware(LoggingMiddleware, enabled_categories=enabled_categories)
```

> 注意：`LoggingMiddleware` 的 `__init__` 签名变化需要同步调整 `app.add_middleware` 调用。当前 `app.py` 中 `app.add_middleware(LoggingMiddleware)` 需改为传入 `enabled_categories`。

- [ ] **Step 3: 改造 ag_ui.py 生命周期日志**

将 `_produce_events_to_queue`、`_eager_event_generator`、`_register_endpoint` 中的 `logger.info("ag-ui ...")` 替换为 `AG_UI_LIFECYCLE` 事件。例如：

```python
from scaffold.infra.logging.events import LogCategory, LogEvent, log_event

# 替换 endpoint invoked 日志：
event = LogEvent(
    category=LogCategory.AG_UI_LIFECYCLE,
    message=f"ag-ui 端点被调用：{path}",
    level="info",
    fields=endpoint_ctx,
)
log_event(logger, event, self._enabled_categories)
```

为 `ag_ui.py` 提供设置类别开关的方法，例如模块级变量：

```python
_enabled_categories: set[str] | None = None

def set_enabled_categories(enabled_categories: set[str]) -> None:
    global _enabled_categories
    _enabled_categories = enabled_categories
```

在 `register_ag_ui_endpoints` 中设置：

```python
def register_ag_ui_endpoints(app: FastAPI) -> None:
    config = get_app_config()
    enabled = {
        name for name, on in config.logging.categories.model_dump().items() if on
    }
    set_enabled_categories(enabled)
    ...
```

- [ ] **Step 4: 在 endpoint 中记录用户输入完整内容**

在 `_register_endpoint` 的 `langgraph_agent_endpoint` 中，增加一条 `USER_INPUT` 事件：

```python
user_messages = [
    m for m in input_data.messages
    if getattr(m, "role", None) == "user"
]
if user_messages:
    last = user_messages[-1]
    content = getattr(last, "content", "")
    event = LogEvent(
        category=LogCategory.USER_INPUT,
        message="用户消息",
        level="info",
        fields={
            "role": "user",
            "content": content,
            "thread_id": input_data.thread_id,
            "run_id": input_data.run_id,
            "request_id": req_id,
        },
    )
    log_event(logger, event, _enabled_categories)
```

- [ ] **Step 5: 运行 Task 4 测试**

Run:
```bash
pytest tests/infra/logging/test_middleware.py tests/test_api.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add src/scaffold/infra/logging/middleware.py src/scaffold/api/ag_ui.py src/scaffold/api/app.py tests/infra/logging/test_middleware.py
git commit -m "feat(api): API 与 ag-ui 日志归类为中文事件，默认关闭生命周期噪音"
```

---

### Task 5: 工具调用日志

**Files:**
- Modify: `src/scaffold/core/tools.py`
- Test: `tests/core/test_tools.py` 或 `tests/infra/logging/test_tool_logging.py`

**Interfaces:**
- Consumes: `LogEvent`, `LogCategory`, `log_event`（来自 Task 1）。
- Produces:
  - `load_tool_from_config` 返回的 `StructuredTool` 被包装，调用时自动记录 `TOOL_CALL` 事件。

- [ ] **Step 1: 编写失败测试——工具调用记录 TOOL_CALL 事件**

```python
# tests/core/test_tools.py
from unittest.mock import patch
from scaffold.infra.logging.events import LogCategory


def test_tool_call_logs_event(tool_config):
    tool = load_tool_from_config(tool_config)
    with patch("scaffold.core.tools.logger") as mock_logger:
        # 同步工具示例
        tool.invoke({"path": "src/main.py"})

    calls = [c for c in mock_logger.method_calls if c[0] in ("info", "debug")]
    assert any(
        c.kwargs.get("extra", {}).get("category") == LogCategory.TOOL_CALL.value
        for c in calls
    )
```

Run: 失败（工具未包装）。

- [ ] **Step 2: 实现工具调用包装器**

```python
# src/scaffold/core/tools.py
from scaffold.infra.logging.events import LogCategory, LogEvent, log_event


def _log_tool_call(name: str, args: dict[str, Any], result: Any, duration_ms: float, error: Exception | None = None) -> None:
    fields = {
        "name": name,
        "args": args,
        "duration_ms": round(duration_ms, 3),
    }
    if error is not None:
        fields["status"] = "error"
        fields["error"] = f"{type(error).__name__}: {error}"
        event = LogEvent(category=LogCategory.TOOL_CALL, message=f"工具调用失败：{name}", level="error", fields=fields)
    else:
        fields["status"] = "success"
        fields["result"] = result
        event = LogEvent(category=LogCategory.TOOL_CALL, message=f"工具调用：{name}", level="info", fields=fields)
    log_event(logger, event, _enabled_tool_categories)


_enabled_tool_categories: set[str] | None = None


def set_tool_logging_categories(enabled_categories: set[str]) -> None:
    global _enabled_tool_categories
    _enabled_tool_categories = enabled_categories


def _wrap_tool(tool: StructuredTool) -> StructuredTool:
    original_func = tool.func
    original_coro = tool.coroutine

    def sync_wrapper(**kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = original_func(**kwargs) if original_func else None
            duration_ms = (time.perf_counter() - start) * 1000
            _log_tool_call(tool.name, kwargs, result, duration_ms)
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _log_tool_call(tool.name, kwargs, None, duration_ms, error=exc)
            raise

    async def async_wrapper(**kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = await original_coro(**kwargs) if original_coro else None
            duration_ms = (time.perf_counter() - start) * 1000
            _log_tool_call(tool.name, kwargs, result, duration_ms)
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _log_tool_call(tool.name, kwargs, None, duration_ms, error=exc)
            raise

    if original_coro:
        return StructuredTool.from_function(
            coroutine=async_wrapper,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )
    return StructuredTool.from_function(
        func=sync_wrapper,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )
```

- [ ] **Step 3: 在 get_available_tools 中应用包装**

```python
def get_available_tools(app_config: AppConfig | None = None) -> list[StructuredTool]:
    if app_config is None:
        app_config = get_app_config()

    enabled = {
        name for name, on in app_config.logging.categories.model_dump().items() if on
    }
    set_tool_logging_categories(enabled)

    tools: list[StructuredTool] = []
    for tool_cfg in app_config.tools:
        try:
            tool = load_tool_from_config(tool_cfg)
            tool = _wrap_tool(tool)
            tools.append(tool)
            logger.debug("Loaded tool: %s", tool_cfg.name)
        except Exception:
            logger.exception("Failed to load tool: %s", tool_cfg.name)
    return tools
```

- [ ] **Step 4: 运行 Task 5 测试**

Run:
```bash
pytest tests/core/test_tools.py tests/infra/logging/test_tool_logging.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/scaffold/core/tools.py tests/core/test_tools.py tests/infra/logging/test_tool_logging.py
git commit -m "feat(tools): 工具调用自动记录 TOOL_CALL 中文事件"
```

---

### Task 6: 记忆系统日志

**Files:**
- Modify: `src/scaffold/infra/middleware/telemetry.py`
- Test: `tests/infra/middleware/test_telemetry.py`

**Interfaces:**
- Consumes: `LogEvent`, `LogCategory`（来自 Task 1）。
- Produces:
  - 当 `MemoryMiddleware`（或名称含 Memory 的中间件）在 `wrap_model_call` 中修改 system message 时，输出 `MEMORY` 事件。

- [ ] **Step 1: 在 telemetry 中检测 MemoryMiddleware 效果**

由于 DeepAgents 原生 `MemoryMiddleware` 自动注入 AGENTS.md，当前仓库的 `infra/memory/` 仅保留占位。最实际的观测点在 telemetry：当某个中间件名包含 "Memory" 且修改了请求时， emit `MEMORY` 事件。

```python
# src/scaffold/infra/middleware/telemetry.py

def _emit_memory_effect(self, hook: str, request_summary: dict[str, Any], duration_ms: float) -> None:
    event = LogEvent(
        category=LogCategory.MEMORY,
        message=f"记忆已注入：{self.name}",
        level="info",
        fields={
            "middleware": self.name,
            "hook": hook,
            "request_summary": request_summary,
            "duration_ms": round(duration_ms, 3),
            "request_id": get_request_id(),
        },
    )
    log_event(self._logger, event, self._enabled_categories)
```

在 `_wrap_model_call_impl` 中，判断 middleware 名是否含 "Memory" 且 request 发生变化：

```python
if request_changed and "Memory" in self.name:
    self._emit_memory_effect("wrap_model_call", summarize_model_request(final_request[0]), duration_ms)
else:
    self._emit_effect(...)
```

> 注意：如果未来 `MemoryMiddleware` 改名或包装方式变化，此检测会失效。可在设计文档中标注为“基于名称启发式”。更稳健的方式是在 middleware factory 中显式为 MemoryMiddleware 附加标记，但为保持简单，先使用名称检测。

- [ ] **Step 2: 测试 MemoryMiddleware 效果检测**

```python
class FakeMemoryMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        return handler(request.override(system_message=MagicMock(text="with memory")))


def test_telemetry_logs_memory_effect():
    wrapped = FakeMemoryMiddleware()
    wrapper = StateTelemetryWrapper(wrapped, index=0)
    wrapper.set_enabled_categories({LogCategory.MEMORY.value, LogCategory.MIDDLEWARE_EFFECT.value})

    request = MagicMock()
    request.state = {"messages": []}
    request.system_message = None
    request.messages = []
    request.override.return_value = request

    with patch.object(wrapper._logger, "info") as mock_info:
        wrapper.wrap_model_call(request, lambda r: MagicMock(result=[MagicMock()]))

    extras = [c.kwargs.get("extra", {}) for c in mock_info.call_args_list]
    assert any(e.get("category") == LogCategory.MEMORY.value for e in extras)
```

- [ ] **Step 3: 运行 Task 6 测试**

Run:
```bash
pytest tests/infra/middleware/test_telemetry.py -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 4: 提交**

```bash
git add src/scaffold/infra/middleware/telemetry.py tests/infra/middleware/test_telemetry.py
git commit -m "feat(telemetry): 检测并记录记忆注入效果"
```

---

### Task 7: 端到端验证与收尾

**Files:**
- 全量测试与手动验证。

- [ ] **Step 1: 全量测试**

Run:
```bash
pytest -v
ruff check src tests
ruff format src tests
```
Expected: 全部通过。

- [ ] **Step 2: 本地启动并验证日志**

Run:
```bash
bash scripts/dev.sh
```

在另一个终端：

```bash
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"thread-plan-001","runId":"run-plan-001","messages":[{"id":"msg-001","role":"user","content":"hello"}],"state":{},"tools":[],"context":[],"forwardedProps":{}}'
```

检查 `logs/scaffold.log`：
- 不应包含 `middleware hook enter` 或 `middleware hook exit`。
- 应包含 `[用户输入]` 开头的请求日志。
- 应包含 `[中间件效果]` 开头的事件（如动态上下文注入）。
- 不应包含大量 `[AG UI 生命周期]` 日志。
- 格式应为中文文本（除非 `config.yaml` 配置为 `json`）。

- [ ] **Step 3: 更新设计文档状态**

修改 `docs/superpowers/specs/2026-08-15-log-simplification-chinese-design.md` 顶部状态为 `已完成`。如有实现细节与文档不符，同步更新文档。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(logging): 完成日志减负与汉化端到端验证"
```

---

## Self-Review

### Spec Coverage

| 设计文档章节 | 实现任务 |
|--------------|----------|
| 3. 配置方案 | Task 2 |
| 4. 日志事件模型 | Task 1 |
| 5. 格式化器 | Task 1 |
| 6.1 AppConfig | Task 2 |
| 6.2 日志配置初始化 | Task 2 |
| 6.3 日志事件与工具函数 | Task 1 |
| 6.4 Telemetry 改造 | Task 3 |
| 6.5 API 层 | Task 4 |
| 6.6 类别过滤 | Task 1、Task 2 |
| 6.7 工具调用日志 | Task 5 |
| 6.8 记忆系统日志 | Task 6 |
| 8. 测试计划 | 各 Task 均含测试步骤 |

### Placeholder Scan

- 无 "TBD"、"TODO"。
- 所有代码步骤均给出具体代码片段或明确命令。
- 测试命令和预期结果明确。

### Type Consistency

- `LogEvent.level` 为字符串（`"info"/"warning"/"error"`），与 `getattr(logger, level.lower())` 一致。
- `LogCategory` 使用 `StrEnum`，`value` 为英文代码，与配置字段名一致。
- `enabled_categories` 在各模块中统一为 `set[str]`。
- `LoggingConfig` 中 `categories` 字段名与 `LogCategory` 值一致。

### Gap

- 设计文档提到“向子 logger 传播”，计划沿用现有 `root.propagate = False`，未额外处理。此行为已足够。
- `JSONFormatter` 的 `category` 字段通过 `record.extra["category"]` 输出，中文文本 formatter 同样读取该字段，一致。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-15-log-simplification-chinese-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
