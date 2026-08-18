"""应用配置系统。

从 deerflow.config.app_config 简化而来，用于 scaffold。
支持 YAML 配置加载、环境变量替换和热重载。"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Self

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from scaffold.infra.config.backend_config import BackendConfig
from scaffold.infra.config.middleware_config import MiddlewareChainConfig
from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.config.profile_config import ProfilesConfig
from scaffold.infra.config.subagent_config import SubAgentsDefinitionsConfig
from scaffold.infra.config.tool_config import ToolConfig, ToolGroupConfig

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseConfig(BaseModel):
    """数据库配置。"""

    backend: str = Field(default="sqlite", description="sqlite or postgres")
    sqlite_dir: str = Field(default="./data", description="Directory for SQLite files")
    history_db: str | None = Field(
        default=None,
        description="历史消息数据库路径；默认使用 sqlite_dir/history.db",
    )
    # Postgres 字段已省略，按需添加 host/port/user/password/dbname


class MemoryConfig(BaseModel):
    """DeepAgents 原生 MemoryMiddleware 配置。

    仅保留启用开关与 AGENTS.md 文件路径。旧版自动提取 facts 相关字段
    （injection_enabled、debounce_seconds、model_name、max_facts、
    fact_confidence_threshold、max_injection_tokens）已移除。
    """

    enabled: bool = True
    storage_path: str = Field(
        default="./data/AGENTS.md",
        description="DeepAgents MemoryMiddleware 加载的 AGENTS.md 路径",
    )


class SubagentConfig(BaseModel):
    enabled: bool = True
    max_concurrent: int = 3
    timeout_seconds: int = 900


class ChannelPlatformConfig(BaseModel):
    enabled: bool = False


class ChannelsConfig(BaseModel):
    langgraph_url: str = "http://localhost:8000/api"
    gateway_url: str = "http://localhost:8000"
    feishu: ChannelPlatformConfig = Field(default_factory=lambda: ChannelPlatformConfig())
    slack: ChannelPlatformConfig = Field(default_factory=lambda: ChannelPlatformConfig())


class TracingConfig(BaseModel):
    enabled: bool = False
    providers: list[str] = Field(default_factory=list)


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    enable_docs: bool = True


class SkillsConfig(BaseModel):
    path: str = "./plugins/skills"
    container_path: str = "/mnt/skills"


class AgentConfig(BaseModel):
    """编排循环行为配置。"""

    max_iterations: int = Field(
        default=40,
        description="ReAct 循环的最大迭代次数（映射到 LangGraph 的 recursion_limit）",
    )
    drop_error_from_history: bool = Field(
        default=True,
        description="工具/模型执行错误是否从对话历史中剔除，防止毒消息死循环",
    )


class AppConfig(BaseModel):
    """根应用配置。"""

    model_config = ConfigDict(extra="allow")

    config_version: int = 1
    log_level: str = Field(default="info", description="debug/info/warning/error")
    log_format: str = Field(default="text", description="text or json")
    middleware_telemetry: bool = Field(
        default=True,
        description="是否在中间件工厂中自动包装每个中间件以记录结构化可观测日志",
    )
    models: list[ModelConfig] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    tool_groups: list[ToolGroupConfig] = Field(default_factory=list)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    subagents: SubagentConfig = Field(default_factory=SubagentConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    middleware: MiddlewareChainConfig = Field(default_factory=MiddlewareChainConfig)
    profiles: ProfilesConfig = Field(default_factory=ProfilesConfig)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    subagent_definitions: SubAgentsDefinitionsConfig = Field(default_factory=SubAgentsDefinitionsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((m for m in self.models if m.name == name), None)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        return next((t for t in self.tools if t.name == name), None)

    def get_harness_profile(self, name: str) -> Any | None:

        return next(
            (p for p in self.profiles.harness if p.name == name),
            None,
        )

    def get_default_harness_profile(self) -> Any | None:
        if self.profiles.default_harness:
            return self.get_harness_profile(self.profiles.default_harness)
        return self.profiles.harness[0] if self.profiles.harness else None

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {path}")
        env_path = os.getenv("SCAFFOLD_CONFIG_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {path}")
        candidates = [Path("config.yaml"), Path("../config.yaml"), Path("../../config.yaml")]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("config.yaml not found in project root or parent directories")

    @classmethod
    def from_file(cls, config_path: str | None = None) -> Self:
        resolved = cls.resolve_config_path(config_path)
        with open(resolved, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data = cls._resolve_env_variables(data)
        return cls.model_validate(data)

    @classmethod
    def _resolve_env_variables(cls, config: Any) -> Any:
        if isinstance(config, str) and config.startswith("$"):
            env_name = config[1:]
            env_value = os.getenv(env_name)
            if env_value is None:
                logger.warning("Environment variable %s not found, using empty string", env_name)
                return ""
            return env_value
        if isinstance(config, dict):
            return {k: cls._resolve_env_variables(v) for k, v in config.items()}
        if isinstance(config, list):
            return [cls._resolve_env_variables(item) for item in config]
        return config


# 基于 mtime 的单例缓存，支持热重载
_app_config: AppConfig | None = None
_app_config_path: Path | None = None
_app_config_mtime: float | None = None
_current_app_config: ContextVar[AppConfig | None] = ContextVar("scaffold_app_config", default=None)


def _get_config_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def get_app_config(config_path: str | None = None) -> AppConfig:
    """获取应用配置，文件变更时自动重载。"""
    global _app_config, _app_config_path, _app_config_mtime

    runtime_override = _current_app_config.get()
    if runtime_override is not None:
        return runtime_override

    resolved = AppConfig.resolve_config_path(config_path)
    current_mtime = _get_config_mtime(resolved)

    should_reload = _app_config is None or _app_config_path != resolved or _app_config_mtime != current_mtime
    if should_reload:
        if _app_config_path == resolved and _app_config_mtime is not None and current_mtime is not None:
            logger.info("Config file modified, reloading AppConfig")
        _app_config = AppConfig.from_file(str(resolved))
        _app_config_path = resolved
        _app_config_mtime = current_mtime

    return _app_config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    global _app_config, _app_config_path, _app_config_mtime
    _app_config = None
    _app_config_path = None
    _app_config_mtime = None
    return get_app_config(config_path)
