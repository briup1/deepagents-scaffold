"""模型工厂测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scaffold.infra.config.model_config import ModelConfig
from scaffold.infra.models.factory import create_chat_model


@pytest.fixture
def openai_config() -> ModelConfig:
    return ModelConfig(
        name="test-openai",
        display_name="Test OpenAI",
        use="langchain_openai:ChatOpenAI",
        api_key="sk-test",
        model="gpt-4",
    )


def test_bypass_proxy_injects_proxy_free_clients(openai_config: ModelConfig) -> None:
    openai_config.bypass_proxy = True

    with (
        patch("scaffold.infra.models.factory.httpx.Client") as mock_sync,
        patch("scaffold.infra.models.factory.httpx.AsyncClient") as mock_async,
    ):
        mock_sync_instance = MagicMock()
        mock_async_instance = MagicMock()
        mock_sync.return_value = mock_sync_instance
        mock_async.return_value = mock_async_instance

        with patch("scaffold.infra.models.factory._import_class") as mock_import:
            mock_cls = MagicMock()
            mock_cls.model_fields = {"http_client": MagicMock(), "http_async_client": MagicMock()}
            mock_import.return_value = mock_cls

            create_chat_model(openai_config)

            mock_sync.assert_called_once_with(proxy=None)
            mock_async.assert_called_once_with(proxy=None)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["http_client"] is mock_sync_instance
            assert call_kwargs["http_async_client"] is mock_async_instance


def test_bypass_proxy_warns_for_unsupported_provider(openai_config: ModelConfig, caplog) -> None:
    openai_config.bypass_proxy = True

    with patch("scaffold.infra.models.factory._import_class") as mock_import:
        mock_cls = MagicMock()
        # Provider does not expose http_client / http_async_client
        mock_cls.model_fields = {"model": MagicMock()}
        mock_import.return_value = mock_cls

        create_chat_model(openai_config)

        assert "does not support custom http_client/http_async_client" in caplog.text
        call_kwargs = mock_cls.call_args.kwargs
        assert "http_client" not in call_kwargs
        assert "http_async_client" not in call_kwargs


def test_no_bypass_proxy_does_not_inject_clients(openai_config: ModelConfig) -> None:
    openai_config.bypass_proxy = False

    with (
        patch("scaffold.infra.models.factory.httpx.Client") as mock_sync,
        patch("scaffold.infra.models.factory.httpx.AsyncClient") as mock_async,
        patch("scaffold.infra.models.factory._import_class") as mock_import,
    ):
        mock_cls = MagicMock()
        mock_cls.model_fields = {"http_client": MagicMock(), "http_async_client": MagicMock()}
        mock_import.return_value = mock_cls

        create_chat_model(openai_config)

        mock_sync.assert_not_called()
        mock_async.assert_not_called()
        call_kwargs = mock_cls.call_args.kwargs
        assert "http_client" not in call_kwargs
        assert "http_async_client" not in call_kwargs
