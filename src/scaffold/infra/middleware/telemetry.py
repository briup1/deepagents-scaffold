"""中间件可观测性包装器。

在不修改现有中间件的前提下，记录链上每个中间件 hook 进入/退出时的状态变化。
事件 hook 的调用通过表驱动生成，避免手写多份重复的计时/日志逻辑。
"""

from __future__ import annotations

import time
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.context import get_request_id, get_trace_id
from scaffold.infra.logging.structured import get_logger

logger = get_logger("infra.middleware.telemetry")

# 总是包装的简单生命周期 hook（基类默认返回 None，不会破坏 SDK 调用路径）
_STATE_HOOK_PAIRS = [
    ("before_agent", "abefore_agent"),
    ("before_model", "abefore_model"),
    ("after_model", "aafter_model"),
    ("after_agent", "aafter_agent"),
]

# 只有被包装者实际覆盖时才包装的回调式 hook（避免把 before_model 路径强制改走 wrap 路径）
_WRAP_HOOK_PAIRS = [
    ("wrap_model_call", "awrap_model_call"),
    ("wrap_tool_call", "awrap_tool_call"),
]

# 动态子类缓存：被包装中间件类 -> 对应 TelemetryWrapper 子类
_telemetry_wrapper_cls_cache: dict[type, type] = {}


def _is_overridden(cls: type[Any], method_name: str) -> bool:
    """判断 method_name 是否在 cls 的 MRO 中（AgentMiddleware 之前）被真正覆写。"""
    for klass in cls.__mro__:
        if klass is AgentMiddleware:
            return False
        if method_name in klass.__dict__:
            return True
    return False


def _make_lifecycle_method(hook: str, is_async: bool):
    """为生命周期 hook 生成绑定到动态子类的方法。"""
    if is_async:

        async def method(self, state: Any, runtime: Any) -> dict[str, Any] | None:
            return await self._arun_lifecycle_hook(hook, state, runtime)

        return method

    def method(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self._run_lifecycle_hook(hook, state, runtime)

    return method


def _make_wrap_method(hook: str, is_async: bool):
    """为回调式 hook 生成绑定到动态子类的方法。"""
    if is_async:

        async def method(self, request: Any, handler: Any) -> Any:
            return await self._arun_wrap_hook(hook, request, handler)

        return method

    def method(self, request: Any, handler: Any) -> Any:
        return self._run_wrap_hook(hook, request, handler)

    return method


def _make_telemetry_wrapper_cls(wrapped_cls: type[Any]) -> type:
    """为被包装中间件动态创建 TelemetryWrapper 子类。

    ``langchain.agents.create_agent`` 通过 class-level 方法判断中间件是否实现了某个 hook。
    仅把方法绑定到实例上无法被 SDK 发现，因此需要动态子类把真正覆写的 hook 暴露到类层面。
    """
    if wrapped_cls in _telemetry_wrapper_cls_cache:
        return _telemetry_wrapper_cls_cache[wrapped_cls]

    methods: dict[str, Any] = {}

    # 生命周期 hook 仅在被子类覆写 sync 或 async 时暴露，避免产生无意义空节点
    for sync_hook, async_hook in _STATE_HOOK_PAIRS:
        if _is_overridden(wrapped_cls, sync_hook):
            methods[sync_hook] = _make_lifecycle_method(sync_hook, False)
        if _is_overridden(wrapped_cls, async_hook):
            methods[async_hook] = _make_lifecycle_method(async_hook, True)

    # 回调式 hook 仅在被子类覆写时暴露，避免不必要的 wrap 链开销
    for sync_hook, async_hook in _WRAP_HOOK_PAIRS:
        if _is_overridden(wrapped_cls, sync_hook) or _is_overridden(wrapped_cls, async_hook):
            methods[sync_hook] = _make_wrap_method(sync_hook, False)
            methods[async_hook] = _make_wrap_method(async_hook, True)

    wrapper_cls = type(
        f"StateTelemetryWrapper_{wrapped_cls.__name__}",
        (StateTelemetryWrapper,),
        methods,
    )
    _telemetry_wrapper_cls_cache[wrapped_cls] = wrapper_cls
    return wrapper_cls


def _base_hook_name(hook: str) -> str:
    """把 async hook 名还原为 sync 基础名（abefore_agent -> before_agent）。"""
    if hook.startswith("a") and not hook.startswith("awrap_"):
        return hook[1:]
    return hook


def _summarize_message(msg: Any) -> dict[str, Any]:
    """安全摘要一条消息。"""
    if msg is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(msg).__name__}

    role = getattr(msg, "role", None) or getattr(msg, "type", None)
    if role is not None:
        summary["role"] = role

    content = getattr(msg, "content", None)
    if content is not None:
        if isinstance(content, str):
            summary["content_length"] = len(content)
        else:
            summary["content"] = _summarize_value(content)

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        summary["tool_calls_count"] = len(tool_calls)
        summary["tool_names"] = [
            tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None) for tc in tool_calls
        ]

    status = getattr(msg, "status", None)
    if status is not None:
        summary["status"] = status

    return summary


def _summarize_value(value: Any) -> dict[str, Any]:
    """安全摘要任意值。"""
    if value is None:
        return {"type": "None"}
    if isinstance(value, str):
        return {"type": "str", "length": len(value), "preview": value[:120]}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": round(value, 6)}
    if isinstance(value, (list, tuple)):
        return {
            "type": type(value).__name__,
            "len": len(value),
            "items": [_summarize_value(v) for v in value[:10]],
        }
    if isinstance(value, dict):
        return {
            "type": "dict",
            "len": len(value),
            "keys": list(value.keys())[:10],
        }
    return {"type": type(value).__name__, "repr": repr(value)[:200]}


def summarize_state(state: Any) -> dict[str, Any]:
    """摘要 agent state，避免打印完整 messages 导致日志爆炸。"""
    if state is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(state).__name__}

    if isinstance(state, dict):
        summary["keys"] = list(state.keys())
        messages = state.get("messages")
        if messages is not None and isinstance(messages, list):
            summary["messages_count"] = len(messages)
            if messages:
                summary["last_message"] = _summarize_message(messages[-1])

        other: dict[str, Any] = {}
        for key, value in state.items():
            if key == "messages":
                continue
            other[key] = _summarize_value(value)
        if other:
            summary["other_keys"] = other
    else:
        summary["repr"] = repr(state)[:200]

    return summary


def summarize_update(update: dict[str, Any] | None) -> dict[str, Any] | None:
    """摘要 before/after hook 返回的 state update。"""
    if update is None:
        return None
    if not isinstance(update, dict):
        return {"type": type(update).__name__, "repr": repr(update)[:200]}

    result: dict[str, Any] = {"keys": list(update.keys())}
    other: dict[str, Any] = {}

    for key, value in update.items():
        if key == "messages" and isinstance(value, list):
            result["messages_delta_count"] = len(value)
            if value:
                result["last_delta_message"] = _summarize_message(value[-1])
        else:
            other[key] = _summarize_value(value)

    if other:
        result["other_keys"] = other

    return result


def summarize_model_request(request: Any) -> dict[str, Any]:
    """摘要 wrap_model_call 的 ModelRequest。"""
    if request is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(request).__name__}

    if hasattr(request, "state"):
        summary["state"] = summarize_state(request.state)
    if hasattr(request, "system_message"):
        summary["system_message"] = _summarize_message(request.system_message)
    if hasattr(request, "messages") and isinstance(request.messages, list):
        summary["messages_count"] = len(request.messages)
    if hasattr(request, "tools") and hasattr(request.tools, "__len__"):
        summary["tools_count"] = len(request.tools)

    return summary


def summarize_model_response(response: Any) -> dict[str, Any]:
    """摘要 wrap_model_call 的返回值。"""
    if response is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(response).__name__}

    if hasattr(response, "result") and isinstance(response.result, list):
        summary["messages_count"] = len(response.result)
        if response.result:
            summary["last_message"] = _summarize_message(response.result[-1])

    if hasattr(response, "structured_response"):
        summary["structured_response"] = _summarize_value(response.structured_response)

    return summary


def summarize_tool_request(request: Any) -> dict[str, Any]:
    """摘要 wrap_tool_call 的 ToolCallRequest。"""
    if request is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(request).__name__}

    if hasattr(request, "tool_call"):
        tc = request.tool_call
        if isinstance(tc, dict):
            summary["tool_name"] = tc.get("name")
            summary["tool_call_id"] = tc.get("id")
        else:
            summary["tool_name"] = getattr(tc, "name", None)
            summary["tool_call_id"] = getattr(tc, "id", None)

    if hasattr(request, "state"):
        summary["state"] = summarize_state(request.state)

    return summary


def summarize_tool_response(response: Any) -> dict[str, Any]:
    """摘要 wrap_tool_call 的返回值。"""
    if response is None:
        return {"type": "None"}

    summary: dict[str, Any] = {"type": type(response).__name__}

    status = getattr(response, "status", None)
    if status is not None:
        summary["status"] = status

    content = getattr(response, "content", None)
    if content is not None:
        if isinstance(content, str):
            summary["content_length"] = len(content)
        else:
            summary["content"] = _summarize_value(content)

    tool_call_id = getattr(response, "tool_call_id", None)
    if tool_call_id is not None:
        summary["tool_call_id"] = tool_call_id

    return summary


class StateTelemetryWrapper(AgentMiddleware):
    """透明包装中间件实例，记录其 hook 进入/退出时的状态变化。"""

    def __new__(
        cls,
        wrapped: AgentMiddleware[Any, Any, Any],
        index: int,
    ) -> "StateTelemetryWrapper":
        # 基类被直接实例化时，返回被包装类对应的动态子类实例，
        # 使 class-level hook 可被 langchain.agents.create_agent 识别。
        if cls is StateTelemetryWrapper:
            wrapper_cls = _make_telemetry_wrapper_cls(type(wrapped))
            return super().__new__(wrapper_cls)
        return super().__new__(cls)

    def __init__(
        self,
        wrapped: AgentMiddleware[Any, Any, Any],
        index: int,
    ) -> None:
        self._wrapped = wrapped
        self._index = index
        self._logger = logger

    @property
    def name(self) -> str:
        """透传被包装中间件的名称。"""
        return getattr(self._wrapped, "name", self._wrapped.__class__.__name__)

    @property
    def state_schema(self) -> Any:
        return getattr(self._wrapped, "state_schema", super().state_schema)

    @property
    def tools(self) -> Any:
        return getattr(self._wrapped, "tools", [])

    @property
    def transformers(self) -> Any:
        return getattr(self._wrapped, "transformers", ())

    def _base_extra(self, hook: str) -> dict[str, Any]:
        return {
            "middleware": self.name,
            "hook": hook,
            "index": self._index,
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
        }

    def _log_hook_enter(self, hook: str, state_summary: dict[str, Any]) -> None:
        self._logger.debug(
            "middleware hook enter",
            extra={
                **self._base_extra(hook),
                "event": "middleware_hook_enter",
                "state_summary": state_summary,
            },
        )

    def _log_hook_exit(
        self,
        hook: str,
        state_summary: dict[str, Any],
        update_summary: dict[str, Any] | None,
        duration_ms: float,
    ) -> None:
        extra: dict[str, Any] = {
            **self._base_extra(hook),
            "event": "middleware_hook_exit",
            "state_summary": state_summary,
            "duration_ms": round(duration_ms, 3),
        }
        if update_summary is not None:
            extra["update_summary"] = update_summary
        self._logger.info("middleware hook exit", extra=extra)

    def _log_model_call_enter(self, hook: str, request_summary: dict[str, Any]) -> None:
        self._logger.debug(
            "middleware model call enter",
            extra={
                **self._base_extra(hook),
                "event": "middleware_model_call_enter",
                "request_summary": request_summary,
            },
        )

    def _log_model_call_exit(
        self,
        hook: str,
        request_summary: dict[str, Any],
        response_summary: dict[str, Any],
        duration_ms: float,
    ) -> None:
        self._logger.info(
            "middleware model call exit",
            extra={
                **self._base_extra(hook),
                "event": "middleware_model_call_exit",
                "request_summary": request_summary,
                "response_summary": response_summary,
                "duration_ms": round(duration_ms, 3),
            },
        )

    def _log_tool_call_enter(self, hook: str, request_summary: dict[str, Any]) -> None:
        self._logger.debug(
            "middleware tool call enter",
            extra={
                **self._base_extra(hook),
                "event": "middleware_tool_call_enter",
                "request_summary": request_summary,
            },
        )

    def _log_tool_call_exit(
        self,
        hook: str,
        request_summary: dict[str, Any],
        response_summary: dict[str, Any],
        duration_ms: float,
    ) -> None:
        self._logger.info(
            "middleware tool call exit",
            extra={
                **self._base_extra(hook),
                "event": "middleware_tool_call_exit",
                "request_summary": request_summary,
                "response_summary": response_summary,
                "duration_ms": round(duration_ms, 3),
            },
        )

    def _call_wrapped_lifecycle(self, hook: str, state: Any, runtime: Any) -> dict[str, Any] | None:
        """调用被包装中间件的同步生命周期 hook；未覆盖时返回 None。"""
        if _is_overridden(type(self._wrapped), hook):
            return getattr(self._wrapped, hook)(state, runtime)
        return None

    async def _acall_wrapped_lifecycle(self, hook: str, state: Any, runtime: Any) -> dict[str, Any] | None:
        """调用被包装中间件的异步生命周期 hook；无 async 实现时回退到同步。"""
        async_hook = f"a{hook}"
        wrapped_cls = type(self._wrapped)
        if _is_overridden(wrapped_cls, async_hook):
            return await getattr(self._wrapped, async_hook)(state, runtime)
        if _is_overridden(wrapped_cls, hook):
            return getattr(self._wrapped, hook)(state, runtime)
        return None

    def _run_lifecycle_hook(
        self,
        hook: str,
        state: Any,
        runtime: Any,
    ) -> dict[str, Any] | None:
        """执行单个同步生命周期 hook 并记录 telemetry。"""
        base_hook = _base_hook_name(hook)
        start = time.perf_counter()
        self._log_hook_enter(hook, summarize_state(state))
        update = self._call_wrapped_lifecycle(base_hook, state, runtime)
        duration_ms = (time.perf_counter() - start) * 1000
        self._log_hook_exit(hook, summarize_state(state), summarize_update(update), duration_ms)
        return update

    async def _arun_lifecycle_hook(
        self,
        hook: str,
        state: Any,
        runtime: Any,
    ) -> dict[str, Any] | None:
        """执行单个异步生命周期 hook 并记录 telemetry。"""
        base_hook = _base_hook_name(hook)
        start = time.perf_counter()
        self._log_hook_enter(hook, summarize_state(state))
        update = await self._acall_wrapped_lifecycle(base_hook, state, runtime)
        duration_ms = (time.perf_counter() - start) * 1000
        self._log_hook_exit(hook, summarize_state(state), summarize_update(update), duration_ms)
        return update

    def _run_wrap_hook(
        self,
        hook: str,
        request: Any,
        handler: Any,
    ) -> Any:
        """执行单个同步 wrap hook 并记录 telemetry。"""
        start = time.perf_counter()
        request_summary = (
            summarize_model_request(request) if hook.startswith("wrap_model") else summarize_tool_request(request)
        )
        enter_log = self._log_model_call_enter if hook.startswith("wrap_model") else self._log_tool_call_enter
        exit_log = self._log_model_call_exit if hook.startswith("wrap_model") else self._log_tool_call_exit
        summarize_response = summarize_model_response if hook.startswith("wrap_model") else summarize_tool_response

        enter_log(hook, request_summary)

        final_request: list[Any] = [request]

        def wrapped_handler(req: Any) -> Any:
            final_request[0] = req
            return handler(req)

        response = getattr(self._wrapped, hook)(request, wrapped_handler)
        duration_ms = (time.perf_counter() - start) * 1000
        exit_log(
            hook,
            summarize_model_request(final_request[0])
            if hook.startswith("wrap_model")
            else summarize_tool_request(final_request[0]),
            summarize_response(response),
            duration_ms,
        )
        return response

    async def _arun_wrap_hook(
        self,
        hook: str,
        request: Any,
        handler: Any,
    ) -> Any:
        """执行单个异步 wrap hook 并记录 telemetry。"""
        start = time.perf_counter()
        is_model = hook.startswith("wrap_model") or hook.startswith("awrap_model")
        request_summary = summarize_model_request(request) if is_model else summarize_tool_request(request)
        enter_log = self._log_model_call_enter if is_model else self._log_tool_call_enter
        exit_log = self._log_model_call_exit if is_model else self._log_tool_call_exit
        summarize_response = summarize_model_response if is_model else summarize_tool_response

        enter_log(hook, request_summary)

        final_request: list[Any] = [request]

        async def wrapped_handler(req: Any) -> Any:
            final_request[0] = req
            return await handler(req)

        response = await getattr(self._wrapped, hook)(request, wrapped_handler)
        duration_ms = (time.perf_counter() - start) * 1000
        exit_log(
            hook,
            summarize_model_request(final_request[0])
            if hook.startswith("wrap_model")
            else summarize_tool_request(final_request[0]),
            summarize_response(response),
            duration_ms,
        )
        return response
