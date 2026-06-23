"""DeepAgents integration — agent factory and registry.

This module is the core bridge between Deer-Flow infrastructure and
DeepAgents SDK. It uses `deepagents.create_deep_agent()` with full
parameter injection: middleware, profiles, backends, checkpointers,
subagents, skills, and memory.
"""

from __future__ import annotations

import logging
from typing import Any

from deepagents import (
    create_deep_agent as _create_deep_agent,
    DeepAgentState,
)
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from scaffold.core.skills import load_skills, get_skill_names
from scaffold.core.subagents import build_subagents
from scaffold.core.tools import get_available_tools
from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.config.backend_config import BackendConfig
from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.config.profile_config import HarnessProfileConfig
from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.models.factory import create_chat_model

logger = logging.getLogger(__name__)

# In-memory agent registry: name -> CompiledStateGraph
_agent_registry: dict[str, Any] = {}


def create_agent(
    name: str = "default",
    *,
    model_name: str | None = None,
    system_prompt: str | SystemMessage | None = None,
    tools: list[Any] | None = None,
    app_config: AppConfig | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    **kwargs: Any,
) -> Any:
    """Create a DeepAgents agent with full Deer-Flow infrastructure injection.

    Args:
        name: Agent identifier for the registry.
        model_name: Which model config to use (defaults to first configured model).
        system_prompt: Override the default system prompt (str or SystemMessage).
        tools: Additional tools beyond those in config.yaml.
        app_config: AppConfig instance (auto-loaded if omitted).
        checkpointer: LangGraph checkpointer for persistence.
        **kwargs: Extra arguments passed to `deepagents.create_deep_agent`.

    Returns:
        A compiled DeepAgents graph (CompiledStateGraph).
    """
    if app_config is None:
        app_config = get_app_config()

    # Resolve model
    model_cfg = _resolve_model_config(app_config, model_name)
    chat_model = create_chat_model(model_cfg)

    # Resolve tools
    configured_tools = get_available_tools(app_config)
    all_tools = configured_tools + (tools or [])

    # Resolve system prompt
    prompt = _build_system_prompt(system_prompt, app_config)

    # Build middleware chain from config
    middleware = build_middleware_chain(app_config=app_config)

    # Build DeepAgents native middleware (Memory, Skills)
    native_middleware = _build_native_middleware(app_config)
    middleware = list(middleware) + native_middleware

    # Resolve backend
    backend = _build_backend(app_config.backend)

    # Resolve subagents
    subagents = _build_subagents(app_config)

    # Resolve skills
    skills = _build_skills(app_config)

    # Resolve memory sources
    memory = _build_memory_sources(app_config)

    # Build tracing callbacks
    callbacks = _build_tracing_callbacks(app_config)

    # Determine state schema
    state_schema = kwargs.pop("state_schema", None) or DeepAgentState

    logger.info(
        "Creating agent '%s' — model=%s tools=%d middleware=%d subagents=%d skills=%d",
        name,
        model_cfg.name,
        len(all_tools),
        len(middleware),
        len(subagents),
        len(skills) if skills else 0,
    )

    agent = _create_deep_agent(
        model=chat_model,
        tools=all_tools,
        system_prompt=prompt,
        middleware=middleware,
        subagents=subagents,
        skills=skills,
        memory=memory,
        backend=backend,
        checkpointer=checkpointer,
        state_schema=state_schema,
        **kwargs,
    )

    # Attach tracing callbacks for runtime use
    if callbacks:
        agent._scaffold_tracing_callbacks = callbacks  # type: ignore[attr-defined]

    _agent_registry[name] = agent
    logger.info("Agent '%s' created and registered", name)
    return agent


def get_agent(name: str = "default") -> Any:
    """Retrieve a previously created agent from the registry."""
    if name not in _agent_registry:
        raise KeyError(f"Agent '{name}' not found. Call create_agent() first.")
    return _agent_registry[name]


def list_agents() -> list[dict[str, Any]]:
    """List all registered agents."""
    return [{"name": name, "type": type(agent).__name__} for name, agent in _agent_registry.items()]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_model_config(app_config: AppConfig, model_name: str | None) -> ModelConfig:
    """Resolve model configuration by name or default to first configured model."""
    if model_name:
        cfg = app_config.get_model_config(model_name)
        if cfg is None:
            raise ValueError(f"Model '{model_name}' not found in config.yaml")
        return cfg
    if app_config.models:
        return app_config.models[0]
    raise ValueError("No models configured. Add at least one model to config.yaml.")


def _build_system_prompt(
    override: str | SystemMessage | None,
    app_config: AppConfig,
) -> str | SystemMessage | None:
    """Build the final system prompt.

    Priority: user override > harness profile > default scaffold prompt.
    """
    if override is not None:
        return override

    # Check for harness profile prompt
    profile = app_config.get_default_harness_profile()
    if isinstance(profile, HarnessProfileConfig):
        parts: list[str] = []
        if profile.base_system_prompt:
            parts.append(profile.base_system_prompt)
        if profile.system_prompt_suffix:
            parts.append(profile.system_prompt_suffix)
        if parts:
            return "\n\n".join(parts)

    # Default scaffold prompt
    return (
        "You are a helpful AI assistant running in the DeepAgents Scaffold. "
        "Use the available tools when needed, think step by step, and be concise."
    )


def _build_native_middleware(app_config: AppConfig) -> list[Any]:
    """Build DeepAgents native middleware (MemoryMiddleware, SkillsMiddleware)."""
    native: list[Any] = []

    # MemoryMiddleware
    if app_config.memory.enabled:
        try:
            from deepagents.backends.filesystem import FilesystemBackend

            backend = FilesystemBackend(root_dir="/")
            memory_mw = MemoryMiddleware(
                backend=backend,
                sources=[app_config.memory.storage_path],
            )
            native.append(memory_mw)
            logger.debug("Enabled MemoryMiddleware")
        except Exception:
            logger.exception("Failed to initialize MemoryMiddleware")

    # SkillsMiddleware
    try:
        skill_names = get_skill_names(app_config)
        if skill_names:
            skills_mw = SkillsMiddleware(skills=skill_names)
            native.append(skills_mw)
            logger.debug("Enabled SkillsMiddleware for %d skills", len(skill_names))
    except Exception:
        logger.exception("Failed to initialize SkillsMiddleware")

    return native


def _build_backend(backend_config: BackendConfig) -> Any | None:
    """Build a DeepAgents backend from configuration."""
    if backend_config.type == "filesystem":
        try:
            from deepagents.backends.filesystem import FilesystemBackend

            return FilesystemBackend(root_dir=backend_config.filesystem.root_dir)
        except Exception:
            logger.exception("Failed to create FilesystemBackend")
            return None
    if backend_config.type == "sandbox":
        logger.warning("Sandbox backend not yet implemented in scaffold")
        return None
    if backend_config.type == "composite":
        logger.warning("Composite backend not yet implemented in scaffold")
        return None
    return None


def _build_subagents(app_config: AppConfig) -> list[Any]:
    """Build subagent definitions from config."""
    if not app_config.subagents.enabled:
        return []
    return build_subagents(app_config)


def _build_skills(app_config: AppConfig) -> list[str] | None:
    """Build skill name list from config."""
    try:
        return get_skill_names(app_config)
    except Exception:
        logger.debug("No skills configured")
        return None


def _build_memory_sources(app_config: AppConfig) -> list[str] | None:
    """Build memory source paths from config."""
    if not app_config.memory.enabled:
        return None
    sources = []
    if app_config.memory.storage_path:
        sources.append(app_config.memory.storage_path)
    return sources if sources else None


def _build_tracing_callbacks(app_config: AppConfig) -> list[Any]:
    """Build LangChain callback handlers from tracing config."""
    callbacks: list[Any] = []
    if not app_config.tracing.enabled:
        return callbacks

    for provider in app_config.tracing.providers:
        if provider == "langsmith":
            try:
                from langsmith import Client as LangSmithClient
                from langchain.callbacks.tracers import LangChainTracer

                callbacks.append(LangChainTracer(client=LangSmithClient()))
                logger.debug("Enabled LangSmith tracing")
            except Exception:
                logger.exception("Failed to initialize LangSmith tracer")
        elif provider == "langfuse":
            try:
                from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

                callbacks.append(LangfuseCallbackHandler())
                logger.debug("Enabled Langfuse tracing")
            except Exception:
                logger.exception("Failed to initialize Langfuse tracer")
    return callbacks
