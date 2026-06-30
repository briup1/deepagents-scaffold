"""模型故障回退中间件适配器。"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.model_fallback import ModelFallbackMiddleware
from langchain.agents.middleware.types import AgentMiddleware

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.middleware.deerflow_adapters._retry_utils import _extract_thread_id
from scaffold.infra.models.factory import create_chat_model

logger = logging.getLogger(__name__)


def _resolve_model_by_name(name: str, models: list[ModelConfig]) -> ModelConfig:
    """按名称在模型配置列表中查找对应配置。"""
    for model in models:
        if model.name == name:
            return model
    available = [m.name for m in models]
    raise ValueError(f"Model '{name}' not found in configured models. Available: {available}")


class ModelFallbackAdapter(AgentMiddleware):
    """主模型失败时自动切换到备选模型。

    Args:
        models: 全部模型配置列表，通过 ``$config.models`` 注入。
        fallback_models: 按 ``ModelConfig.name`` 引用的备选模型名称列表。
    """

    def __init__(
        self,
        *,
        models: list[ModelConfig],
        fallback_models: list[str],
    ) -> None:
        fallback_chat_models = [create_chat_model(_resolve_model_by_name(name, models)) for name in fallback_models]
        self._middleware = ModelFallbackMiddleware(*fallback_chat_models)
        logger.info(
            "ModelFallbackAdapter initialized with fallback models: %s",
            fallback_models,
        )

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return self._middleware.wrap_model_call(request, self._wrap_handler(request, handler))

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await self._middleware.awrap_model_call(request, self._wrap_handler(request, handler))

    def _wrap_handler(self, request: Any, handler: Any) -> Any:
        """Wrap handler to log each fallback model being tried."""
        thread_id = _extract_thread_id(request)
        is_first = True

        def wrapped(req: Any) -> Any:
            nonlocal is_first
            model_name = self._model_name(req)
            if not is_first:
                logger.warning(
                    "Falling back to model '%s' for thread_id=%s",
                    model_name,
                    thread_id,
                )
            is_first = False
            return handler(req)

        async def awrapped(req: Any) -> Any:
            nonlocal is_first
            model_name = self._model_name(req)
            if not is_first:
                logger.warning(
                    "Falling back to model '%s' for thread_id=%s",
                    model_name,
                    thread_id,
                )
            is_first = False
            return await handler(req)

        import inspect

        return awrapped if inspect.iscoroutinefunction(handler) else wrapped

    @staticmethod
    def _model_name(request: Any) -> str:
        model = getattr(request, "model", None)
        if model is None:
            return "unknown"
        return getattr(model, "model", getattr(model, "model_name", "unknown"))
