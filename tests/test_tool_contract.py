"""校验所有在 config 中注册的 LLM 可调用工具满足异步 + **kwargs 契约。"""

from __future__ import annotations

import inspect

import pytest

from scaffold.core.tools import get_available_tools


async def test_all_registered_tools_are_async_and_accept_kwargs():
    """所有注册工具的底层可调用对象必须是 async 且接受 **kwargs。"""
    tools = get_available_tools()
    assert tools, "config 中未注册任何工具"

    failures = []
    for tool in tools:
        func = getattr(tool, "coroutine", None) or getattr(tool, "func", None)
        if func is None:
            failures.append(f"{tool.name}: 无法获取底层可调用对象")
            continue

        if not inspect.iscoroutinefunction(func):
            failures.append(f"{tool.name}: 底层函数 {func.__name__} 不是 async")

        sig = inspect.signature(func)
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            failures.append(f"{tool.name}: 底层函数 {func.__name__} 不接受 **kwargs")

    if failures:
        pytest.fail("工具契约校验失败:\n" + "\n".join(f"  - {msg}" for msg in failures))
