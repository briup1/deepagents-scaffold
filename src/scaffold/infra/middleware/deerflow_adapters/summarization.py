"""Summarization middleware adapter.

本模块把 ``langchain.agents.middleware`` 提供的生产级 ``SummarizationMiddleware``
包装成适合本脚手架配置的版本：自动从 ``config.yaml`` 解析要使用的 LLM，
其余参数（``trigger`` / ``keep`` / ``trim_tokens_to_summarize`` 等）全部透传给上游实现。

上游实现会：
- 根据 ``trigger`` 阈值（消息数 / 绝对 token / 模型最大输入比例）决定是否摘要；
- 使用独立的 LLM 调用生成结构化摘要（SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS）；
- 通过 ``RemoveMessage(id=REMOVE_ALL_MESSAGES)`` 清空旧消息，并保留 ``keep`` 指定的近期消息；
- 在截断时保护 ``AIMessage.tool_calls`` 与对应 ``ToolMessage`` 不被拆散。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.summarization import (
    SummarizationMiddleware as _LangChainSummarizationMiddleware,
)

logger = logging.getLogger(__name__)


class SummarizationMiddleware(_LangChainSummarizationMiddleware):
    """自动注入模型配置的 SummarizationMiddleware 包装器。

    Args:
        model_name: 要用于摘要的模型名称（对应 ``config.yaml`` 中 ``models`` 的
            ``name`` 字段）。为 ``None`` 时使用第一个已配置的模型。
        **kwargs: 其余参数全部透传给
            ``langchain.agents.middleware.summarization.SummarizationMiddleware``。
            常用参数：

            - ``trigger``: 触发摘要的阈值，例如
              ``[("messages", 200), ("tokens", 6000)]``。
            - ``keep``: 摘要后保留的近期消息，例如 ``("messages", 20)``。
            - ``trim_tokens_to_summarize``: 生成摘要前对旧消息做截断的 token 上限。
            - ``summary_prompt``: 自定义摘要生成 prompt。
    """

    def __init__(
        self,
        *,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        from scaffold.infra.config.app_config import get_app_config
        from scaffold.infra.models.factory import create_chat_model

        app_config = get_app_config()

        if model_name is not None:
            model_cfg = app_config.get_model_config(model_name)
            if model_cfg is None:
                raise ValueError(
                    f"Model '{model_name}' not found in config.yaml. "
                    f"Available models: {[m.name for m in app_config.models]}"
                )
        else:
            if not app_config.models:
                raise ValueError(
                    "No models configured in config.yaml. "
                    "SummarizationMiddleware requires at least one model."
                )
            model_cfg = app_config.models[0]

        model = create_chat_model(model_cfg)
        logger.info(
            "SummarizationMiddleware initialized with model '%s' (%s)",
            model_cfg.name,
            model_cfg.use,
        )
        super().__init__(model=model, **kwargs)
