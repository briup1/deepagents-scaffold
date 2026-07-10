"""DeepAgents 集成 —— agent 工厂与注册表。

本模块是 Deer-Flow 基础设施与 DeepAgents SDK 之间的核心桥梁。
它通过 `deepagents.create_deep_agent()` 注入全部可注入参数：
中间件（middleware）、配置画像（profiles）、后端（backends）、检查点器（checkpointers）、
子 agent（subagents）、技能（skills）以及记忆（memory）。
"""

from __future__ import annotations

import logging
from typing import Any

from deepagents import (
    create_deep_agent as _create_deep_agent,
    DeepAgentState,
)

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from scaffold.core.skills import get_skill_names
from scaffold.core.subagents import build_subagents
from scaffold.core.tools import get_available_tools
from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.config.backend_config import BackendConfig
from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.config.profile_config import HarnessProfileConfig
from scaffold.infra.middleware.factory import build_middleware_chain
from scaffold.infra.models.factory import create_chat_model
from scaffold.infra.prompts.assembler import PromptAssembler

logger = logging.getLogger(__name__)

# 内存中的 agent 注册表：名称 -> CompiledStateGraph
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
    """创建 DeepAgents agent，并注入完整的 Deer-Flow 基础设施参数。

    Args:
        name: agent 在注册表中的标识名称。
        model_name: 使用的模型配置名称（默认取第一个已配置的模型）。
        system_prompt: 覆盖默认系统提示词（字符串或 SystemMessage）。
        tools: 除 config.yaml 中配置之外额外附加的工具列表。
        app_config: AppConfig 实例（省略时自动加载）。
        checkpointer: 用于持久化的 LangGraph 检查点器。
        **kwargs: 额外参数，直接传给 `deepagents.create_deep_agent`。

    Returns:
        编译后的 DeepAgents 图（CompiledStateGraph）。
    """
    if app_config is None:
        app_config = get_app_config()

    # 解析模型配置
    model_cfg = _resolve_model_config(app_config, model_name)
    chat_model = create_chat_model(model_cfg)

    # 解析工具
    configured_tools = get_available_tools(app_config)
    all_tools = configured_tools + (tools or [])

    # 解析系统提示词
    prompt = _build_system_prompt(system_prompt, app_config)

    # 根据配置构建中间件链
    middleware = build_middleware_chain(app_config=app_config)

    # 构建 DeepAgents 原生中间件（Memory、Skills）
    native_middleware = _build_native_middleware(app_config)
    middleware = list(middleware) + native_middleware

    # 解析后端
    backend = _build_backend(app_config.backend)

    # 解析子 agent
    subagents = _build_subagents(app_config)

    # 解析技能
    skills = _build_skills(app_config)

    # 解析记忆来源
    memory = _build_memory_sources(app_config)

    # 构建链路追踪回调
    callbacks = _build_tracing_callbacks(app_config)

    # 确定状态 schema
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

    # 附加运行时链路追踪回调
    if callbacks:
        agent._scaffold_tracing_callbacks = callbacks  # type: ignore[attr-defined]

    _agent_registry[name] = agent
    logger.info("Agent '%s' 已创建并注册", name)
    return agent


def get_agent(name: str = "default") -> Any:
    """从注册表中获取先前创建的 agent。"""
    if name not in _agent_registry:
        raise KeyError(f"Agent '{name}' not found. Call create_agent() first.")
    return _agent_registry[name]


def list_agents() -> list[dict[str, Any]]:
    """列出所有已注册的 agent。"""
    return [{"name": name, "type": type(agent).__name__} for name, agent in _agent_registry.items()]


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _resolve_model_config(app_config: AppConfig, model_name: str | None) -> ModelConfig:
    """根据名称解析模型配置，若未指定则默认取第一个已配置的模型。"""
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
    """构建最终系统提示词。

    优先级：用户覆盖 > harness profile > PromptAssembler 默认模板。
    """
    # 优先级 1: 用户直接覆盖
    if override is not None:
        return override

    # 优先级 2: harness profile 配置
    profile = app_config.get_default_harness_profile()
    if isinstance(profile, HarnessProfileConfig):
        assembler = PromptAssembler()

        # 如果 profile 有自定义 prompt，使用 PromptAssembler 组装
        if profile.base_system_prompt or profile.system_prompt_suffix:
            return assembler.assemble(
                custom=profile.base_system_prompt,
                suffix=profile.system_prompt_suffix,
            )

    # 优先级 3: 使用 PromptAssembler 默认模板
    assembler = PromptAssembler()
    return assembler.assemble()


def _build_native_middleware(app_config: AppConfig) -> list[Any]:
    """构建 DeepAgents 原生中间件。

    注意：MemoryMiddleware 和 SkillsMiddleware 已由 create_deep_agent 自动添加
    （通过 memory 和 skills 参数），此处不再重复创建以避免 "duplicate middleware" 错误。
    """
    return []


def _build_backend(backend_config: BackendConfig) -> Any | None:
    """根据配置构建 DeepAgents 后端（backend）。"""
    if backend_config.type == "filesystem":
        try:
            from deepagents.backends.filesystem import FilesystemBackend

            # 显式指定 virtual_mode=False 以保留当前行为（允许绝对路径），
            # 避免 deepagents>=0.6.0 默认值变更时产生 DeprecationWarning。
            return FilesystemBackend(
                root_dir=backend_config.filesystem.root_dir,
                virtual_mode=False,
            )
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
    """根据配置构建子 agent 定义。"""
    if not app_config.subagents.enabled:
        return []
    return build_subagents(app_config)


def _build_skills(app_config: AppConfig) -> list[str] | None:
    """根据配置构建技能名称列表。"""
    try:
        return get_skill_names(app_config)
    except Exception:
        logger.debug("No skills configured")
        return None


def _build_memory_sources(app_config: AppConfig) -> list[str] | None:
    """根据配置构建记忆来源路径。"""
    if not app_config.memory.enabled:
        return None
    sources = []
    if app_config.memory.storage_path:
        sources.append(app_config.memory.storage_path)
    return sources if sources else None


def _build_tracing_callbacks(app_config: AppConfig) -> list[Any]:
    """根据链路追踪配置构建 LangChain 回调处理器。"""
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
