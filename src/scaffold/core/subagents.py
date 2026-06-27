"""子 Agent 系统。

从 config.yaml 加载子 agent 定义，并构建 DeepAgents 所需的
SubAgent TypedDict 实例，供 create_deep_agent(subagents=[...]) 使用。
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.core.tools import get_available_tools
from scaffold.infra.config.app_config import AppConfig
from scaffold.infra.config.subagent_config import SubAgentDefinitionConfig
from scaffold.infra.middleware.registry import get_middleware_registry
from scaffold.infra.models.factory import create_chat_model
from scaffold.infra.config.app_config import get_app_config

logger = logging.getLogger(__name__)


def build_subagents(app_config: AppConfig | None = None) -> list[Any]:
    """根据 config.yaml 中的定义构建 DeepAgents SubAgent 实例。

    Args:
        app_config: 包含子 agent 定义的 AppConfig。

    Returns:
        供 create_deep_agent() 使用的 SubAgent TypedDict 列表。
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
    """根据配置构建单个 DeepAgents SubAgent。"""
    from deepagents.middleware.subagents import SubAgent

    # 解析工具
    tools = _resolve_tools(cfg.tools, app_config)

    # 解析模型覆盖配置
    model = None
    if cfg.model:
        model_cfg = app_config.get_model_config(cfg.model)
        if model_cfg:
            model = create_chat_model(model_cfg)
        else:
            # 尝试 provider:model 字符串格式
            try:
                from langchain.chat_models import init_chat_model

                model = init_chat_model(cfg.model)
            except Exception:
                logger.warning("Could not resolve model '%s' for subagent '%s'", cfg.model, cfg.name)

    # 解析中间件
    middleware = []
    for mw_name in cfg.middleware:
        try:
            registry = get_middleware_registry()
            cls = registry.resolve(mw_name)
            middleware.append(cls())
        except Exception:
            logger.warning("Could not resolve middleware '%s' for subagent '%s'", mw_name, cfg.name)

    # 构建 SubAgent 规格
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
    """将工具名称解析为实际工具实例。"""
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
