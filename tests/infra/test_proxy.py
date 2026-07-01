"""代理环境变量兼容处理测试。"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

from scaffold.infra.proxy import configure_proxy_environment


@pytest.fixture(autouse=True)
def _clean_env():
    """每个用例前清理相关代理变量。"""
    for var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(var, None)
    yield
    for var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(var, None)


def test_normalizes_socks_scheme():
    os.environ["ALL_PROXY"] = "socks://127.0.0.1:7897/"

    with patch.object(importlib.util, "find_spec", return_value=True):
        configure_proxy_environment()

    assert os.environ["ALL_PROXY"] == "socks5://127.0.0.1:7897/"


def test_keeps_existing_socks5_scheme():
    os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7897/"

    with patch.object(importlib.util, "find_spec", return_value=True):
        configure_proxy_environment()

    assert os.environ["ALL_PROXY"] == "socks5://127.0.0.1:7897/"


def test_removes_socks_when_socksio_missing():
    os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7897/"

    with patch.object(importlib.util, "find_spec", return_value=None):
        configure_proxy_environment()

    assert "ALL_PROXY" not in os.environ


def test_keeps_socks_when_socksio_present():
    os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7897/"

    with patch.object(importlib.util, "find_spec", return_value=True):
        configure_proxy_environment()

    assert os.environ["ALL_PROXY"] == "socks5://127.0.0.1:7897/"


def test_handles_lowercase_all_proxy_var():
    os.environ["all_proxy"] = "socks://127.0.0.1:7897/"

    with patch.object(importlib.util, "find_spec", return_value=True):
        configure_proxy_environment()

    assert os.environ["all_proxy"] == "socks5://127.0.0.1:7897/"
