"""Tests for the prompt engineering system."""

from __future__ import annotations

from scaffold.infra.prompts.assembler import PromptAssembler
from scaffold.infra.prompts.loader import PromptLoader
from scaffold.infra.prompts.registry import PromptRegistry


class TestPromptRegistry:
    def test_register_and_get(self):
        reg = PromptRegistry()
        reg.register("test", "Hello")
        assert reg.get("test") == "Hello"
        assert reg.get("missing") is None

    def test_build_simple(self):
        reg = PromptRegistry()
        reg.register("base", "Base prompt")
        result = reg.build(user_prompt="User prompt", base_name="base")
        assert "User prompt" in result
        assert "Base prompt" in result


class TestPromptAssembler:
    def test_assemble_order(self):
        asm = PromptAssembler()
        result = asm.assemble(
            user="USER",
            base="BASE",
            custom="CUSTOM",
            suffix="SUFFIX",
        )
        assert result.index("USER") < result.index("CUSTOM")
        assert result.index("CUSTOM") < result.index("SUFFIX")


class TestPromptLoader:
    def test_load_nonexistent_dir(self):
        loader = PromptLoader("/nonexistent/path")
        reg = loader.load_all()
        assert reg.list_names() == []
