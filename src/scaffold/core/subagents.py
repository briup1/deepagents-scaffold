"""SubAgent system.

Loads subagent definitions from config.yaml and builds DeepAgents
SubAgent TypedDict instances for create_deep_agent(subagents=[...]).
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.core.tools import get_available_tools
from scaffold.infra.config.app_config import AppConfig
from scaffold.infra.config.subagent_config import SubAgentDefinitionConfig
from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.middleware.registry import get_middleware_registry
from scaffold.infra.models.factory import create_chat_model
from scaffold.infra.config.app_config import get_app_config

logger = logging.getLogger(__name__)


def build_subagents(app_config: AppConfig | None = None) -> list[Any]:
    """Build DeepAgents SubAgent instances from config.yaml definitions.

    Args:
        app_config: AppConfig with subagent definitions.

    Returns:
        List of SubAgent TypedDicts for create_deep_agent().
    """
    if app_config is None:
        app_config = get_app_config()

    if not app_config.subagents.enabled:
        return []

    definitions = getattr(app_config, "subagent_definitions", None)
    if definitions is None:
        return []

    subagents: list[Any] = []
    for cfg in definitions.get_enabled():
        try:
            subagent = _build_single_subagent(cfg, app_config)
            if subagent:
                subagents.append(subagent)
                logger.info("Built subagent: %s", cfg.name)
        except Exception:
            logger.exception("Failed to build subagent '%s', skipping", cfg.name)

    return subagents


def _build_single_subagent(
    cfg: SubAgentDefinitionConfig,
    app_config: AppConfig,
) -> Any | None:
    """Build a single DeepAgents SubAgent from config."""
    from deepagents.middleware.subagents import SubAgent

    # Resolve tools
    tools = _resolve_tools(cfg.tools, app_config)

    # Resolve model override
    model = None
    if cfg.model:
        model_cfg = app_config.get_model_config(cfg.model)
        if model_cfg:
            model = create_chat_model(model_cfg)
        else:
            # Try provider:model string format
            try:
                from langchain.chat_models import init_chat_model

                model = init_chat_model(cfg.model)
            except Exception:
                logger.warning("Could not resolve model '%s' for subagent '%s'", cfg.model, cfg.name)

    # Resolve middleware
    middleware = []
    for mw_name in cfg.middleware:
        try:
            registry = get_middleware_registry()
            cls = registry.resolve(mw_name)
            middleware.append(cls())
        except Exception:
            logger.warning("Could not resolve middleware '%s' for subagent '%s'", mw_name, cfg.name)

    # Build SubAgent spec
    spec: dict[str, Any] = {
        "name": cfg.name,
        "description": cfg.description,
        "system_prompt": cfg.system_prompt,
    }
    if tools:
        spec["tools"] = tools
    if model is not None:
        spec["model"] = model
    if middleware:
        spec["middleware"] = middleware
    if cfg.skills:
        spec["skills"] = cfg.skills
    if cfg.interrupt_on:
        spec["interrupt_on"] = cfg.interrupt_on

    return SubAgent(**spec)


def _resolve_tools(tool_names: list[str], app_config: AppConfig) -> list[Any]:
    """Resolve tool names to actual tool instances."""
    if not tool_names:
        return []

    all_tools = get_available_tools(app_config)
    tool_map = {t.name: t for t in all_tools}

    resolved = []
    for name in tool_names:
        if name in tool_map:
            resolved.append(tool_map[name])
        else:
            logger.warning("Tool '%s' not found for subagent", name)

    return resolved
