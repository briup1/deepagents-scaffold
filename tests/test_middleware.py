"""Tests for the middleware framework."""

from __future__ import annotations

import pytest

from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from scaffold.infra.middleware.deerflow_adapters.safety_termination import SafetyTerminationMiddleware
from scaffold.infra.middleware.deerflow_adapters.tool_error_handling import ToolErrorHandlingMiddleware
from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.middleware.registry import get_middleware_registry


class TestMiddlewareRegistry:
    def test_resolve_known_alias(self):
        registry = get_middleware_registry()
        cls = registry.resolve("LoopDetectionMiddleware")
        assert cls.__name__ == "LoopDetectionMiddleware"

    def test_resolve_by_import_path(self):
        registry = get_middleware_registry()
        cls = registry.resolve(
            "scaffold.infra.middleware.deerflow_adapters.tool_error_handling:ToolErrorHandlingMiddleware"
        )
        assert cls.__name__ == "ToolErrorHandlingMiddleware"

    def test_resolve_unknown_raises(self):
        registry = get_middleware_registry()
        with pytest.raises(ValueError, match="Unknown middleware alias"):
            registry.resolve("NonExistentMiddleware")

    def test_list_known(self):
        registry = get_middleware_registry()
        names = registry.list_known()
        assert "LoopDetectionMiddleware" in names
        assert "ToolErrorHandlingMiddleware" in names


class TestMiddlewareFactory:
    def test_empty_chain(self):
        from scaffold.infra.config.middleware_config import MiddlewareChainConfig

        chain = MiddlewareChainConfig(items=[])
        result = build_middleware_chain(chain)
        assert result == []


class TestScaffoldSummarizationMiddleware:
    def test_alias_resolves(self):
        registry = get_middleware_registry()
        cls = registry.resolve("ScaffoldSummarizationMiddleware")
        assert cls.__name__ == "ScaffoldSummarizationMiddleware"

    def test_wrapper_injects_model_from_config(self, monkeypatch):
        import scaffold.infra.config.app_config as app_config_module
        import scaffold.infra.models.factory as model_factory_module

        fake_model = type("FakeModel", (), {"_llm_type": "fake"})()

        class FakeModelConfig:
            name = "fake-model"
            use = "fake:FakeModel"

        class FakeAppConfig:
            models = [FakeModelConfig()]

            def get_model_config(self, name):
                return FakeModelConfig() if name == "fake-model" else None

        monkeypatch.setattr(app_config_module, "get_app_config", lambda config_path=None: FakeAppConfig())
        calls = []

        def fake_create_chat_model(cfg, **kwargs):
            calls.append(cfg)
            return fake_model

        monkeypatch.setattr(model_factory_module, "create_chat_model", fake_create_chat_model)

        cls = get_middleware_registry().resolve("ScaffoldSummarizationMiddleware")
        instance = cls(model_name="fake-model", trigger=[("messages", 100)], keep=("messages", 10))

        assert len(calls) == 1
        assert calls[0].name == "fake-model"
        assert instance.model is fake_model


class TestToolErrorHandlingMiddleware:
    def test_wrap_tool_call_converts_exception_to_error_tool_message(self):
        mw = ToolErrorHandlingMiddleware()
        request = ToolCallRequest(
            tool_call={"id": "call-1", "name": "bad_tool"},
            tool=None,
            state={},
            runtime=None,
        )

        def failing_handler(request):
            raise ValueError("tool exploded")

        result = mw.wrap_tool_call(request, failing_handler)

        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "call-1"
        assert result.status == "error"
        assert "ValueError: tool exploded" in result.content

    async def test_awrap_tool_call_converts_exception_to_error_tool_message(self):
        mw = ToolErrorHandlingMiddleware()
        request = ToolCallRequest(
            tool_call={"id": "call-2", "name": "async_bad_tool"},
            tool=None,
            state={},
            runtime=None,
        )

        async def failing_handler(request):
            raise RuntimeError("async tool exploded")

        result = await mw.awrap_tool_call(request, failing_handler)

        assert isinstance(result, ToolMessage)
        assert result.tool_call_id == "call-2"
        assert result.status == "error"
        assert "RuntimeError: async tool exploded" in result.content

    def test_after_model_drops_error_finish_reason(self):
        mw = ToolErrorHandlingMiddleware(drop_error_from_history=True)
        messages = [
            HumanMessage("hi"),
            AIMessage(content="x", response_metadata={"finish_reason": "error"}),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update == {"messages": [messages[0]]}

    def test_after_model_keeps_normal_finish_reason(self):
        mw = ToolErrorHandlingMiddleware(drop_error_from_history=True)
        messages = [
            HumanMessage("hi"),
            AIMessage(content="ok", response_metadata={"finish_reason": "stop"}),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is None

    def test_after_model_respects_disable_flag(self):
        mw = ToolErrorHandlingMiddleware(drop_error_from_history=False)
        messages = [
            HumanMessage("hi"),
            AIMessage(content="x", response_metadata={"finish_reason": "error"}),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is None

    def test_factory_auto_wires_drop_error_from_history(self, monkeypatch):
        from scaffold.infra.config import middleware_config as middleware_config_module
        from scaffold.infra.config.app_config import AgentConfig, AppConfig

        app_config = AppConfig(
            agent=AgentConfig(max_iterations=40, drop_error_from_history=False),
        )

        chain = build_middleware_chain(
            config=middleware_config_module.MiddlewareChainConfig(
                items=[
                    middleware_config_module.MiddlewareConfig(
                        name="ToolErrorHandlingMiddleware",
                        enabled=True,
                    )
                ]
            ),
            app_config=app_config,
        )

        assert len(chain) == 1
        assert isinstance(chain[0], ToolErrorHandlingMiddleware)
        assert chain[0].drop_error_from_history is False

    def test_factory_allows_explicit_override(self, monkeypatch):
        from scaffold.infra.config import middleware_config as middleware_config_module
        from scaffold.infra.config.app_config import AgentConfig, AppConfig

        app_config = AppConfig(
            agent=AgentConfig(max_iterations=40, drop_error_from_history=False),
        )

        chain = build_middleware_chain(
            config=middleware_config_module.MiddlewareChainConfig(
                items=[
                    middleware_config_module.MiddlewareConfig(
                        name="ToolErrorHandlingMiddleware",
                        enabled=True,
                        kwargs={"drop_error_from_history": True},
                    )
                ]
            ),
            app_config=app_config,
        )

        assert len(chain) == 1
        assert chain[0].drop_error_from_history is True


class TestSafetyTerminationMiddleware:
    def test_no_intervention_without_tool_calls(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("hi"),
            AIMessage(
                content="I cannot help with that policy.",
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is None

    def test_strips_tool_calls_on_content_filter(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("write bad file"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "write_file", "args": {"path": "/tmp/bad"}}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is not None
        patched = update["messages"][-1]
        assert isinstance(patched, AIMessage)
        assert patched.tool_calls == []
        assert "content_filter" in patched.content
        assert "suppressed" in patched.content

    def test_preserves_message_metadata(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("x"),
            AIMessage(
                id="msg-123",
                content="",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "SAFETY", "model_name": "gpt-test"},
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        patched = update["messages"][-1]
        assert patched.id == "msg-123"
        assert patched.response_metadata == {"finish_reason": "SAFETY", "model_name": "gpt-test"}
        assert patched.usage_metadata == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

    def test_records_safety_termination_in_additional_kwargs(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("x"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "write_file", "args": {}}],
                response_metadata={"finish_reason": "refusal"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        patched = update["messages"][-1]
        meta = patched.additional_kwargs["safety_termination"]
        assert meta["reason_field"] == "finish_reason"
        assert meta["reason_value"] == "refusal"
        assert meta["suppressed_tool_call_count"] == 1
        assert meta["suppressed_tool_call_names"] == ["write_file"]

    def test_detects_content_keyword_signal(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("x"),
            AIMessage(
                content="I cannot process this request due to SAFETY policy.",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is not None
        meta = update["messages"][-1].additional_kwargs["safety_termination"]
        assert meta["reason_field"] == "content"
        assert meta["reason_value"] == "SAFETY"

    def test_extra_signals_are_respected(self):
        mw = SafetyTerminationMiddleware(extra_signals=["custom_block"])
        messages = [
            HumanMessage("x"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "custom_block"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is not None
        assert update["messages"][-1].tool_calls == []

    def test_no_intervention_on_normal_stop(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("hi"),
            AIMessage(
                content="Hello!",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "stop"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        assert update is None

    def test_disable_warning_does_not_append_text(self):
        mw = SafetyTerminationMiddleware(emit_warning=False)
        messages = [
            HumanMessage("x"),
            AIMessage(
                content="original",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        patched = update["messages"][-1]
        assert patched.content == "original"
        assert patched.additional_kwargs["safety_termination"]["suppressed_tool_call_count"] == 1

    def test_append_to_list_content(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("x"),
            AIMessage(
                content=[{"type": "text", "text": "partial"}],
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]

        update = mw.after_model({"messages": messages}, runtime=None)

        patched = update["messages"][-1]
        assert isinstance(patched.content, list)
        assert patched.content[0] == {"type": "text", "text": "partial"}
        assert patched.content[-1]["type"] == "text"
        assert "content_filter" in patched.content[-1]["text"]

    async def test_aafter_model_delegates_to_sync(self):
        mw = SafetyTerminationMiddleware()
        messages = [
            HumanMessage("x"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]

        update = await mw.aafter_model({"messages": messages}, runtime=None)

        assert update is not None
        assert update["messages"][-1].tool_calls == []
