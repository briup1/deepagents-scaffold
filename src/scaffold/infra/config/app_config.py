"""Application configuration system.

Simplified from deerflow.config.app_config for the scaffold.
Supports YAML config loading, env-var substitution, and hot-reload.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal, Self

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
    backend: str = Field(default="sqlite", description="sqlite or postgres")
    sqlite_dir: str = Field(default="./data", description="Directory for SQLite files")
    # Postgres fields omitted for brevity; add host/port/user/password/dbname as needed


class StreamBridgeConfig(BaseModel):
    type: Literal["memory"] = Field(default="memory", description="Stream bridge backend type")
    queue_maxsize: int = Field(default=256, description="Maximum size of the internal event queue")


class MemoryConfig(BaseModel):
    enabled: bool = True
    injection_enabled: bool = True
    storage_path: str = "./data/memory.json"
    debounce_seconds: int = 30
    model_name: str | None = None
    max_facts: int = 100
    fact_confidence_threshold: float = 0.7
    max_injection_tokens: int = 2000


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


class AppConfig(BaseModel):
    """Root application configuration."""

    model_config = ConfigDict(extra="allow")

    config_version: int = 1
    log_level: str = Field(default="info", description="debug/info/warning/error")
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
    stream_bridge: StreamBridgeConfig = Field(default_factory=StreamBridgeConfig)

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((m for m in self.models if m.name == name), None)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        return next((t for t in self.tools if t.name == name), None)

    def get_harness_profile(self, name: str) -> Any | None:
        from scaffold.infra.config.profile_config import HarnessProfileConfig

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
            env_value = os.getenv(config[1:])
            if env_value is None:
                raise ValueError(f"Environment variable {config[1:]} not found")
            return env_value
        if isinstance(config, dict):
            return {k: cls._resolve_env_variables(v) for k, v in config.items()}
        if isinstance(config, list):
            return [cls._resolve_env_variables(item) for item in config]
        return config

    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((m for m in self.models if m.name == name), None)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        return next((t for t in self.tools if t.name == name), None)


# Singleton cache with mtime-based hot reload
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
    """Get the application config, auto-reloading when the file changes."""
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
