"""DeepAgents 原生 SummarizationMiddleware 的可配置适配器。

本模块把 DeepAgents 内部自动注入的 ``SummarizationMiddleware`` 暴露为可由
``config.yaml`` 驱动的形式，支持自定义 ``summary_prompt``、
``trim_tokens_to_summarize``、``token_counter`` 等参数，同时保留 DeepAgents
原生的 backend offload、ContextOverflowError fallback、tool-args 预截断等增强。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Sequence
from typing import Any

from deepagents.backends import StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.summarization import (
    DEFAULT_SUMMARY_PROMPT,
    SummarizationMiddleware as _DeepAgentsSummarizationMiddleware,
    compute_summarization_defaults,
    count_tokens_approximately,
)
from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.models.factory import create_chat_model

logger = logging.getLogger(__name__)

TokenCounter = Callable[[Sequence[Any]], int]
ContextSize = tuple[str, int | float]


def _resolve_callable(value: Any | str) -> Any:
    """把字符串导入路径解析为可调用对象，非字符串则原样返回。"""
    if not isinstance(value, str):
        return value
    if ":" not in value:
        return value
    module_path, attr_name = value.split(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def _is_context_size(value: Any) -> bool:
    """判断一个值是否是单个 ContextSize 规格（如 ``("messages", 30)``）。"""
    return isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], str)


def _to_context_size(value: Any) -> ContextSize:
    """把 YAML 列表/tuple 转成 DeepAgents 要求的 ContextSize tuple。"""
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"Invalid context size spec: {value!r}")
    return value  # type: ignore[return-value]


def _normalize_trigger(value: Any) -> ContextSize | list[ContextSize]:
    """统一 trigger 参数：单规格或列表规格都能接受。"""
    if _is_context_size(value):
        return _to_context_size(value)
    if isinstance(value, list):
        return [_to_context_size(v) for v in value]
    raise ValueError(f"Invalid trigger spec: {value!r}")


def _build_backend_for_middleware(app_config: AppConfig) -> Any:
    """根据 ``app_config.backend`` 构造一个 DeepAgents backend 实例。

    目前仅支持 ``filesystem``；``sandbox`` / ``composite`` 留待后续实现。
    """
    backend_cfg = app_config.backend
    if backend_cfg.type == "filesystem":
        return FilesystemBackend(root_dir=backend_cfg.filesystem.root_dir)
    if backend_cfg.type == "sandbox":
        raise NotImplementedError("DeepAgentsSummarizationMiddleware does not yet support sandbox backend")
    if backend_cfg.type == "composite":
        raise NotImplementedError("DeepAgentsSummarizationMiddleware does not yet support composite backend")
    return StateBackend()


class DeepAgentsSummarizationMiddleware(_DeepAgentsSummarizationMiddleware):
    """可由 ``config.yaml`` 配置的原生 DeepAgents 摘要中间件。

    DeepAgents 的 ``create_deep_agent`` 默认会注入一个 ``SummarizationMiddleware``，
    但其参数由模型 profile 自动计算，无法通过配置文件调整。本适配器继承该原生类，
    因此保留全部原生行为；同时允许在 ``config.yaml`` 中显式传参。

    使用时需要在 harness profile 中先排除默认的 ``"SummarizationMiddleware"``，
    再在 ``middleware.items`` 中启用本别名，否则会因为 ``.name`` 相同而触发重复校验。

    Args:
        model_name: 用于生成摘要的模型名称（对应 ``config.models[].name``）。
            为 ``None`` 时使用第一个已配置模型。
        trigger: 触发摘要的阈值，例如 ``("messages", 30)`` 或
            ``[("fraction", 0.8), ("messages", 100)]``。
        keep: 摘要后保留的近期上下文，例如 ``("messages", 5)``。
        summary_prompt: 摘要生成 prompt 模板。
        trim_tokens_to_summarize: 生成摘要前对旧消息截断的 token 上限。
        token_counter: token 计数函数。可以是函数本身，也可以是
            ``module.path:callable`` 形式的导入路径字符串。
        truncate_args_settings: 大 tool-args 预截断配置。
        backend: 可选的外部 backend 实例。未提供时根据 ``app_config.backend``
            自动构造。
    """

    def __init__(
        self,
        *,
        model_name: str | None = None,
        trigger: ContextSize | list[ContextSize] | None = None,
        keep: ContextSize | None = None,
        summary_prompt: str | None = None,
        trim_tokens_to_summarize: int | None = None,
        token_counter: TokenCounter | str | None = None,
        truncate_args_settings: dict[str, Any] | None = None,
        backend: Any | None = None,
    ) -> None:
        app_config = get_app_config()

        model_cfg = app_config.get_model_config(model_name) if model_name else app_config.models[0]
        if model_cfg is None:
            raise ValueError(
                f"Model '{model_name}' not found in config.yaml. Available: {[m.name for m in app_config.models]}"
            )

        model = create_chat_model(model_cfg)
        resolved_backend = backend or _build_backend_for_middleware(app_config)

        defaults = compute_summarization_defaults(model)

        resolved_trigger = _normalize_trigger(trigger) if trigger is not None else defaults["trigger"]
        resolved_keep = _to_context_size(keep) if keep is not None else defaults["keep"]
        resolved_summary_prompt = summary_prompt if summary_prompt is not None else DEFAULT_SUMMARY_PROMPT
        resolved_token_counter = (
            _resolve_callable(token_counter) if token_counter is not None else count_tokens_approximately
        )
        resolved_truncate_args = (
            truncate_args_settings if truncate_args_settings is not None else defaults["truncate_args_settings"]
        )

        logger.info(
            "DeepAgentsSummarizationMiddleware initialized with model '%s' trigger=%s keep=%s",
            model_cfg.name,
            resolved_trigger,
            resolved_keep,
        )

        super().__init__(
            model=model,
            backend=resolved_backend,
            trigger=resolved_trigger,
            keep=resolved_keep,
            summary_prompt=resolved_summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
            token_counter=resolved_token_counter,
            truncate_args_settings=resolved_truncate_args,
        )
