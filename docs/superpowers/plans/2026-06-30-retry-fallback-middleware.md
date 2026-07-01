# 模型重试、工具重试与模型回退中间件实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Deer-Flow 适配器架构下新增三个韧性中间件（模型重试、工具重试、模型回退），并通过 `MiddlewareRegistry` 别名暴露给 `config.yaml` 使用。

**Architecture:** 在 `src/scaffold/infra/middleware/deerflow_adapters/` 中新增薄适配器类，接收 scaffold 风格的配置，内部实例化并委托给 LangChain 原生 `ModelRetryMiddleware` / `ToolRetryMiddleware` / `ModelFallbackMiddleware`。共享的重试判断逻辑抽取到 `_retry_utils.py`。`registry.py` 为每个适配器注册一个人类可读的别名。

**Tech Stack:** Python 3.12, LangChain agents middleware, DeepAgents scaffold, pytest, ruff.

## Global Constraints

- 配置是 `config.yaml` 的唯一事实来源。
- 中间件通过 `MiddlewareRegistry` 注册别名。
- 尽量复用 LangChain/DeepAgents 原生实现，只在外围做薄适配。
- 异步优先。
- 仅补充单元测试。
- 命名：snake_case（函数/变量），PascalCase（类）。
- 类型：完整类型注解。
- 格式：ruff（line-length=120, target-version=py312）。

## File Structure

### 新增文件

- `src/scaffold/infra/middleware/deerflow_adapters/_retry_utils.py`
  - 共享重试判断函数 `_build_retry_predicate`。
  - 共享的 `thread_id` 提取辅助函数 `_extract_thread_id`。
- `src/scaffold/infra/middleware/deerflow_adapters/model_retry.py`
  - `ModelRetryAdapter`，包装 LangChain `ModelRetryMiddleware`。
- `src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py`
  - `ToolRetryAdapter`，包装 LangChain `ToolRetryMiddleware`。
- `src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py`
  - `ModelFallbackAdapter`，把 `fallback_models` 名称解析为 `BaseChatModel` 后包装 LangChain `ModelFallbackMiddleware`。
- `tests/infra/middleware/deerflow_adapters/test_retry_utils.py`
- `tests/infra/middleware/deerflow_adapters/test_model_retry.py`
- `tests/infra/middleware/deerflow_adapters/test_tool_retry.py`
- `tests/infra/middleware/deerflow_adapters/test_model_fallback.py`

### 修改文件

- `src/scaffold/infra/middleware/registry.py`
  - 在 `_DEFAULT_MIDDLEWARE_MAP` 中注册 `ModelRetryMiddleware`、`ToolRetryMiddleware`、`ModelFallbackMiddleware` 别名。
- `config.yaml`
  - 在 `middleware.items` 末尾添加注释掉的示例声明，方便用户按需启用，同时不破坏默认开发启动。

## Task 1: 共享重试判断工具

**Files:**
- Create: `src/scaffold/infra/middleware/deerflow_adapters/_retry_utils.py`
- Create: `tests/infra/middleware/deerflow_adapters/test_retry_utils.py`

**Interfaces:**
- Produces:
  - `_build_retry_predicate(status_codes: list[int]) -> Callable[[Exception], bool]`
  - `_extract_thread_id(request: ModelRequest[Any]) -> str | None`

- [x] **Step 1: Write the failing test**

```python
"""Tests for shared retry utilities."""

from __future__ import annotations

import pytest

from scaffold.infra.middleware.deerflow_adapters._retry_utils import (
    _build_retry_predicate,
    _extract_thread_id,
)


class TestBuildRetryPredicate:
    def test_status_code_match_returns_true(self):
        predicate = _build_retry_predicate([429, 502])

        class FakeException(Exception):
            status_code = 429

        assert predicate(FakeException("rate limited")) is True

    def test_status_code_miss_returns_false(self):
        predicate = _build_retry_predicate([429, 502])

        class FakeException(Exception):
            status_code = 500

        assert predicate(FakeException("server error")) is False

    def test_business_exception_returns_false(self):
        predicate = _build_retry_predicate([429, 502])

        assert predicate(ValueError("bad input")) is False


class TestExtractThreadId:
    def test_extracts_from_runtime_context(self):
        class FakeRuntime:
            context = {"thread_id": "thread-123"}

        class FakeRequest:
            runtime = FakeRuntime()

        assert _extract_thread_id(FakeRequest()) == "thread-123"

    def test_returns_none_when_runtime_is_none(self):
        class FakeRequest:
            runtime = None

        assert _extract_thread_id(FakeRequest()) is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_retry_utils.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scaffold.infra.middleware.deerflow_adapters._retry_utils'`

- [x] **Step 3: Write minimal implementation**

```python
"""Shared helpers for retry and fallback middleware adapters."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_retry_predicate(status_codes: list[int]):
    """Build a callable that decides whether an exception should be retried.

    Matches first by ``status_code`` attribute, then by known provider
    rate-limit/timeout exception types. Business exceptions like ``ValueError``
    are not retried.
    """
    status_set = set(status_codes)

    def should_retry(exc: Exception) -> bool:
        code = getattr(exc, "status_code", None)
        if code is not None and code in status_set:
            logger.warning("Retry predicate matched status_code=%s", code)
            return True

        # Delayed imports keep the helper usable even when a provider
        # package is not installed.
        for module_path, class_name in (
            ("openai", "RateLimitError"),
            ("openai", "APITimeoutError"),
            ("openai", "InternalServerError"),
            ("anthropic", "RateLimitError"),
            ("anthropic", "APITimeoutError"),
            ("anthropic", "InternalServerError"),
            ("httpx", "TimeoutException"),
            ("httpx", "ConnectError"),
        ):
            try:
                module = __import__(module_path, fromlist=[class_name])
                exc_cls = getattr(module, class_name)
                if isinstance(exc, exc_cls):
                    logger.warning(
                        "Retry predicate matched provider exception %s.%s",
                        module_path,
                        class_name,
                    )
                    return True
            except Exception:
                continue

        return False

    return should_retry


def _extract_thread_id(request: Any) -> str | None:
    """Extract thread_id from a ModelRequest's runtime context, if available."""
    runtime = getattr(request, "runtime", None)
    if runtime is None:
        return None
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        return context.get("thread_id")
    return None
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_retry_utils.py -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff format src/scaffold/infra/middleware/deerflow_adapters/_retry_utils.py tests/infra/middleware/deerflow_adapters/test_retry_utils.py
uv run ruff check src/scaffold/infra/middleware/deerflow_adapters/_retry_utils.py tests/infra/middleware/deerflow_adapters/test_retry_utils.py
git add src/scaffold/infra/middleware/deerflow_adapters/_retry_utils.py tests/infra/middleware/deerflow_adapters/test_retry_utils.py
git commit -m "feat: add shared retry predicate helper for resilience middleware"
```

## Task 2: ModelRetryAdapter

**Files:**
- Create: `src/scaffold/infra/middleware/deerflow_adapters/model_retry.py`
- Modify: `src/scaffold/infra/middleware/registry.py:17-35`
- Create: `tests/infra/middleware/deerflow_adapters/test_model_retry.py`

**Interfaces:**
- Consumes:
  - `_build_retry_predicate` from `_retry_utils.py`
  - `_extract_thread_id` from `_retry_utils.py`
  - `ModelRetryMiddleware` from `langchain.agents.middleware.model_retry`
- Produces:
  - `ModelRetryAdapter` class registered as `ModelRetryMiddleware` alias.

- [x] **Step 1: Write the failing test**

```python
"""Tests for ModelRetryAdapter."""

from __future__ import annotations

import logging

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage

from scaffold.infra.middleware.deerflow_adapters.model_retry import ModelRetryAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestModelRetryAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ModelRetryMiddleware")
        assert cls.__name__ == "ModelRetryAdapter"

    def test_default_params(self):
        mw = ModelRetryAdapter()
        assert mw._middleware.max_retries == 2
        assert mw._middleware.backoff_factor == 2.0
        assert mw._middleware.initial_delay == 1.0
        assert mw._middleware.max_delay == 60.0
        assert mw._middleware.jitter is True
        assert mw._middleware.on_failure == "continue"

    def test_custom_params(self):
        mw = ModelRetryAdapter(
            max_retries=5,
            backoff_factor=1.5,
            initial_delay=0.5,
            max_delay=30.0,
            jitter=False,
            retry_on_status_codes=[503],
        )
        assert mw._middleware.max_retries == 5
        assert mw._middleware.backoff_factor == 1.5
        assert mw._middleware.initial_delay == 0.5
        assert mw._middleware.max_delay == 30.0
        assert mw._middleware.jitter is False

    def test_wrap_model_call_delegates(self):
        mw = ModelRetryAdapter()
        expected = AIMessage(content="ok")

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])
        result = mw.wrap_model_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_model_call_delegates(self):
        mw = ModelRetryAdapter()
        expected = AIMessage(content="ok")

        class FakeMiddleware:
            async def awrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])

        async def handler(req):
            return expected

        result = await mw.awrap_model_call(request, handler)
        assert result is expected

    def test_logging_handler_logs_failed_attempt(self, caplog):
        mw = ModelRetryAdapter()

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return handler(request)

        mw._middleware = FakeMiddleware()

        class FakeException(Exception):
            status_code = 429

        class FakeRuntime:
            context = {"thread_id": "thread-abc"}

        request = ModelRequest(model=None, messages=[], runtime=FakeRuntime())

        with caplog.at_level(logging.WARNING):
            with pytest.raises(FakeException):
                mw.wrap_model_call(
                    request,
                    lambda req: (_ for _ in ()).throw(FakeException("rate limited")),
                )

        assert "thread-abc" in caplog.text
        assert "429" in caplog.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_model_retry.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scaffold.infra.middleware.deerflow_adapters.model_retry'`

- [x] **Step 3: Write minimal implementation**

Create `src/scaffold/infra/middleware/deerflow_adapters/model_retry.py`:

```python
"""模型调用重试中间件适配器。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.model_retry import ModelRetryMiddleware
from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.middleware.deerflow_adapters._retry_utils import (
    _build_retry_predicate,
    _extract_thread_id,
)

logger = logging.getLogger(__name__)

_DEFAULT_STATUS_CODES = [429, 502, 503, 504]


class ModelRetryAdapter(AgentMiddleware):
    """模型调用失败时按指数退避重试。

    Args:
        max_retries: 初始调用之外的最大重试次数。默认 2。
        backoff_factor: 退避倍数。默认 2.0。
        initial_delay: 首次重试前等待秒数。默认 1.0。
        max_delay: 退避增长上限。默认 60.0。
        jitter: 是否加入 ±25% 随机抖动。默认 True。
        retry_on_status_codes: 触发重试的 HTTP 状态码列表。
            默认 [429, 502, 503, 504]。
    """

    def __init__(
        self,
        *,
        max_retries: int = 2,
        backoff_factor: float = 2.0,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_on_status_codes: list[int] | None = None,
    ) -> None:
        self._middleware = ModelRetryMiddleware(
            max_retries=max_retries,
            retry_on=_build_retry_predicate(retry_on_status_codes or _DEFAULT_STATUS_CODES),
            on_failure="continue",
            backoff_factor=backoff_factor,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return self._middleware.wrap_model_call(request, self._wrap_sync_handler(request, handler))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await self._middleware.awrap_model_call(
            request, self._wrap_async_handler(request, handler)
        )

    def _wrap_sync_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        def wrapped(req: Any) -> Any:
            try:
                return handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Model call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped

    def _wrap_async_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        async def wrapped(req: Any) -> Any:
            try:
                return await handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Model call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped
```

Modify `src/scaffold/infra/middleware/registry.py` to add the `ModelRetryMiddleware` alias inside `_DEFAULT_MIDDLEWARE_MAP` (place it near the Deer-Flow adapters block):

```python
    "ModelRetryMiddleware": "scaffold.infra.middleware.deerflow_adapters.model_retry:ModelRetryAdapter",
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_model_retry.py -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff format src/scaffold/infra/middleware/deerflow_adapters/model_retry.py tests/infra/middleware/deerflow_adapters/test_model_retry.py src/scaffold/infra/middleware/registry.py
uv run ruff check src/scaffold/infra/middleware/deerflow_adapters/model_retry.py tests/infra/middleware/deerflow_adapters/test_model_retry.py src/scaffold/infra/middleware/registry.py
git add src/scaffold/infra/middleware/deerflow_adapters/model_retry.py tests/infra/middleware/deerflow_adapters/test_model_retry.py src/scaffold/infra/middleware/registry.py
git commit -m "feat: add ModelRetryAdapter with registry alias"
```

## Task 3: ToolRetryAdapter

**Files:**
- Create: `src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py`
- Modify: `src/scaffold/infra/middleware/registry.py:17-35`
- Create: `tests/infra/middleware/deerflow_adapters/test_tool_retry.py`

**Interfaces:**
- Consumes:
  - `_build_retry_predicate` from `_retry_utils.py`
  - `_extract_thread_id` from `_retry_utils.py`
  - `ToolRetryMiddleware` from `langchain.agents.middleware.tool_retry`
- Produces:
  - `ToolRetryAdapter` class registered as `ToolRetryMiddleware` alias.

- [x] **Step 1: Write the failing test**

```python
"""Tests for ToolRetryAdapter."""

from __future__ import annotations

import logging

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from scaffold.infra.middleware.deerflow_adapters.tool_retry import ToolRetryAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestToolRetryAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ToolRetryMiddleware")
        assert cls.__name__ == "ToolRetryAdapter"

    def test_default_max_retries_is_one(self):
        mw = ToolRetryAdapter()
        assert mw._middleware.max_retries == 1
        assert mw._middleware.jitter is True

    def test_custom_params(self):
        mw = ToolRetryAdapter(max_retries=3, retry_on_status_codes=[429])
        assert mw._middleware.max_retries == 3

    def test_wrap_tool_call_delegates(self):
        mw = ToolRetryAdapter()
        expected = ToolMessage(content="ok", tool_call_id="call-1")

        class FakeMiddleware:
            def wrap_tool_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "tool"},
            tool=None,
            state={},
            runtime=None,
        )
        result = mw.wrap_tool_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_tool_call_delegates(self):
        mw = ToolRetryAdapter()
        expected = ToolMessage(content="ok", tool_call_id="call-2")

        class FakeMiddleware:
            async def awrap_tool_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ToolCallRequest(
            tool_call={"id": "call-2", "name": "tool"},
            tool=None,
            state={},
            runtime=None,
        )

        async def handler(req):
            return expected

        result = await mw.awrap_tool_call(request, handler)
        assert result is expected

    def test_logging_handler_logs_failed_attempt(self, caplog):
        mw = ToolRetryAdapter()

        class FakeMiddleware:
            def wrap_tool_call(self, request, handler):
                return handler(request)

        mw._middleware = FakeMiddleware()

        class FakeException(Exception):
            status_code = 502

        class FakeRuntime:
            context = {"thread_id": "thread-tool"}

        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "tool"},
            tool=None,
            state={},
            runtime=FakeRuntime(),
        )

        with caplog.at_level(logging.WARNING):
            with pytest.raises(FakeException):
                mw.wrap_tool_call(
                    request,
                    lambda req: (_ for _ in ()).throw(FakeException("bad gateway")),
                )

        assert "thread-tool" in caplog.text
        assert "502" in caplog.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_tool_retry.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scaffold.infra.middleware.deerflow_adapters.tool_retry'`

- [x] **Step 3: Write minimal implementation**

Create `src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py`:

```python
"""工具调用重试中间件适配器。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.tool_retry import ToolRetryMiddleware
from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.middleware.deerflow_adapters._retry_utils import (
    _build_retry_predicate,
    _extract_thread_id,
)

logger = logging.getLogger(__name__)

_DEFAULT_STATUS_CODES = [429, 502, 503, 504]


class ToolRetryAdapter(AgentMiddleware):
    """工具调用失败时按指数退避重试。

    Args:
        max_retries: 初始调用之外的最大重试次数。默认 1。
        backoff_factor: 退避倍数。默认 2.0。
        initial_delay: 首次重试前等待秒数。默认 1.0。
        max_delay: 退避增长上限。默认 60.0。
        jitter: 是否加入 ±25% 随机抖动。默认 True。
        retry_on_status_codes: 触发重试的 HTTP 状态码列表。
            默认 [429, 502, 503, 504]。
    """

    def __init__(
        self,
        *,
        max_retries: int = 1,
        backoff_factor: float = 2.0,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_on_status_codes: list[int] | None = None,
    ) -> None:
        self._middleware = ToolRetryMiddleware(
            max_retries=max_retries,
            retry_on=_build_retry_predicate(retry_on_status_codes or _DEFAULT_STATUS_CODES),
            on_failure="continue",
            backoff_factor=backoff_factor,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        return self._middleware.wrap_tool_call(request, self._wrap_sync_handler(request, handler))

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        return await self._middleware.awrap_tool_call(
            request, self._wrap_async_handler(request, handler)
        )

    def _wrap_sync_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        def wrapped(req: Any) -> Any:
            try:
                return handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Tool call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped

    def _wrap_async_handler(self, request: Any, handler: Any) -> Any:
        thread_id = _extract_thread_id(request)

        async def wrapped(req: Any) -> Any:
            try:
                return await handler(req)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                logger.warning(
                    "Tool call failed and will be retried: thread_id=%s status_code=%s exc=%s",
                    thread_id,
                    status_code,
                    type(exc).__name__,
                )
                raise

        return wrapped
```

Modify `src/scaffold/infra/middleware/registry.py` to add the `ToolRetryMiddleware` alias inside `_DEFAULT_MIDDLEWARE_MAP`:

```python
    "ToolRetryMiddleware": "scaffold.infra.middleware.deerflow_adapters.tool_retry:ToolRetryAdapter",
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_tool_retry.py -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff format src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py tests/infra/middleware/deerflow_adapters/test_tool_retry.py src/scaffold/infra/middleware/registry.py
uv run ruff check src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py tests/infra/middleware/deerflow_adapters/test_tool_retry.py src/scaffold/infra/middleware/registry.py
git add src/scaffold/infra/middleware/deerflow_adapters/tool_retry.py tests/infra/middleware/deerflow_adapters/test_tool_retry.py src/scaffold/infra/middleware/registry.py
git commit -m "feat: add ToolRetryAdapter with registry alias"
```

## Task 4: ModelFallbackAdapter

**Files:**
- Create: `src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py`
- Modify: `src/scaffold/infra/middleware/registry.py:17-35`
- Create: `tests/infra/middleware/deerflow_adapters/test_model_fallback.py`

**Interfaces:**
- Consumes:
  - `ModelConfig` from `scaffold.infra.config.model_config`
  - `create_chat_model` from `scaffold.infra.models.factory`
  - `_extract_thread_id` from `_retry_utils.py`
  - `ModelFallbackMiddleware` from `langchain.agents.middleware.model_fallback`
- Produces:
  - `ModelFallbackAdapter` class registered as `ModelFallbackMiddleware` alias.

- [x] **Step 1: Write the failing test**

```python
"""Tests for ModelFallbackAdapter."""

from __future__ import annotations

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.middleware.deerflow_adapters.model_fallback import ModelFallbackAdapter
from scaffold.infra.middleware.registry import get_middleware_registry


class TestModelFallbackAdapter:
    def test_registry_alias_resolves(self):
        cls = get_middleware_registry().resolve("ModelFallbackMiddleware")
        assert cls.__name__ == "ModelFallbackAdapter"

    def test_resolves_fallback_models_and_creates_middleware(self, monkeypatch):
        calls = []

        def fake_create_chat_model(config, **kwargs):
            calls.append(config)
            return type(f"Fake{config.name}", (), {"model": config.model})()

        monkeypatch.setattr(
            "scaffold.infra.middleware.deerflow_adapters.model_fallback.create_chat_model",
            fake_create_chat_model,
        )

        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
            ModelConfig(name="fallback-1", display_name="Fallback 1", use="fake:Fallback1", model="fallback-1"),
        ]

        mw = ModelFallbackAdapter(models=models, fallback_models=["fallback-1"])

        assert len(calls) == 1
        assert calls[0].name == "fallback-1"
        assert len(mw._middleware.models) == 1

    def test_unknown_fallback_model_raises(self):
        models = [
            ModelConfig(name="primary", display_name="Primary", use="fake:Primary", model="primary"),
        ]

        with pytest.raises(ValueError, match="Model 'missing' not found"):
            ModelFallbackAdapter(models=models, fallback_models=["missing"])

    def test_wrap_model_call_delegates(self):
        mw = ModelFallbackAdapter.__new__(ModelFallbackAdapter)
        expected = AIMessage(content="fallback ok")

        class FakeMiddleware:
            def wrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])
        result = mw.wrap_model_call(request, lambda req: expected)
        assert result is expected

    async def test_awrap_model_call_delegates(self):
        mw = ModelFallbackAdapter.__new__(ModelFallbackAdapter)
        expected = AIMessage(content="fallback ok")

        class FakeMiddleware:
            async def awrap_model_call(self, request, handler):
                return expected

        mw._middleware = FakeMiddleware()

        request = ModelRequest(model=None, messages=[])

        async def handler(req):
            return expected

        result = await mw.awrap_model_call(request, handler)
        assert result is expected
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_model_fallback.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scaffold.infra.middleware.deerflow_adapters.model_fallback'`

- [x] **Step 3: Write minimal implementation**

Create `src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py`:

```python
"""模型故障回退中间件适配器。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.model_fallback import ModelFallbackMiddleware
from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.middleware.deerflow_adapters._retry_utils import _extract_thread_id
from scaffold.infra.models.factory import create_chat_model

logger = logging.getLogger(__name__)


def _resolve_model_by_name(name: str, models: list[ModelConfig]) -> ModelConfig:
    """按名称在模型配置列表中查找对应配置。"""
    for model in models:
        if model.name == name:
            return model
    available = [m.name for m in models]
    raise ValueError(f"Model '{name}' not found in configured models. Available: {available}")


class ModelFallbackAdapter(AgentMiddleware):
    """主模型失败时自动切换到备选模型。

    Args:
        models: 全部模型配置列表，通过 ``$config.models`` 注入。
        fallback_models: 按 ``ModelConfig.name`` 引用的备选模型名称列表。
    """

    def __init__(
        self,
        *,
        models: list[ModelConfig],
        fallback_models: list[str],
    ) -> None:
        fallback_chat_models = [
            create_chat_model(_resolve_model_by_name(name, models))
            for name in fallback_models
        ]
        self._middleware = ModelFallbackMiddleware(*fallback_chat_models)
        logger.info(
            "ModelFallbackAdapter initialized with fallback models: %s",
            fallback_models,
        )

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return self._middleware.wrap_model_call(request, self._wrap_handler(request, handler))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await self._middleware.awrap_model_call(request, self._wrap_handler(request, handler))

    def _wrap_handler(self, request: Any, handler: Any) -> Any:
        """Wrap handler to log each fallback model being tried."""
        thread_id = _extract_thread_id(request)
        is_first = True

        def wrapped(req: Any) -> Any:
            nonlocal is_first
            model_name = self._model_name(req)
            if not is_first:
                logger.warning(
                    "Falling back to model '%s' for thread_id=%s",
                    model_name,
                    thread_id,
                )
            is_first = False
            return handler(req)

        async def awrapped(req: Any) -> Any:
            nonlocal is_first
            model_name = self._model_name(req)
            if not is_first:
                logger.warning(
                    "Falling back to model '%s' for thread_id=%s",
                    model_name,
                    thread_id,
                )
            is_first = False
            return await handler(req)

        import inspect

        return awrapped if inspect.iscoroutinefunction(handler) else wrapped

    @staticmethod
    def _model_name(request: Any) -> str:
        model = getattr(request, "model", None)
        if model is None:
            return "unknown"
        return getattr(model, "model", getattr(model, "model_name", "unknown"))
```

Modify `src/scaffold/infra/middleware/registry.py` to add the `ModelFallbackMiddleware` alias inside `_DEFAULT_MIDDLEWARE_MAP`:

```python
    "ModelFallbackMiddleware": "scaffold.infra.middleware.deerflow_adapters.model_fallback:ModelFallbackAdapter",
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/infra/middleware/deerflow_adapters/test_model_fallback.py -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
uv run ruff format src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py tests/infra/middleware/deerflow_adapters/test_model_fallback.py src/scaffold/infra/middleware/registry.py
uv run ruff check src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py tests/infra/middleware/deerflow_adapters/test_model_fallback.py src/scaffold/infra/middleware/registry.py
git add src/scaffold/infra/middleware/deerflow_adapters/model_fallback.py tests/infra/middleware/deerflow_adapters/test_model_fallback.py src/scaffold/infra/middleware/registry.py
git commit -m "feat: add ModelFallbackAdapter with registry alias"
```

## Task 5: 更新 config.yaml 示例

**Files:**
- Modify: `config.yaml:76-103`

**Interfaces:**
- Consumes: aliases registered in `registry.py`.

- [x] **Step 1: Add commented example middleware declarations**

Append the following block to the end of `middleware.items` in `config.yaml`, after `ScaffoldSummarizationMiddleware`:

```yaml
    # 韧性中间件（模型重试、工具重试、模型回退）
    # 按需取消注释并调整 fallback_models 为你的实际模型名称。
    # - name: ModelFallbackMiddleware
    #   enabled: true
    #   kwargs:
    #     models: $config.models
    #     fallback_models:
    #       - fallback-model-name
    # - name: ModelRetryMiddleware
    #   enabled: true
    #   kwargs:
    #     max_retries: 2
    #     backoff_factor: 2.0
    #     initial_delay: 1.0
    #     max_delay: 60.0
    #     jitter: true
    #     retry_on_status_codes: [429, 502, 503, 504]
    # - name: ToolRetryMiddleware
    #   enabled: true
    #   kwargs:
    #     max_retries: 1
    #     backoff_factor: 2.0
    #     initial_delay: 1.0
    #     max_delay: 60.0
    #     jitter: true
    #     retry_on_status_codes: [429, 502, 503, 504]
```

- [x] **Step 2: Verify config loads and existing tests still pass**

Run: `uv run pytest tests/test_config.py tests/test_middleware.py -v`

Expected: PASS (config loads, registry aliases are resolvable).

- [x] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "docs: add commented retry/fallback middleware examples to config.yaml"
```

## Final Verification

After all tasks:

```bash
uv run pytest tests/infra/middleware/deerflow_adapters/ -v
uv run pytest tests/test_middleware.py -v
uv run ruff format src tests
uv run ruff check src tests
```

Expected: all tests pass, ruff clean.
