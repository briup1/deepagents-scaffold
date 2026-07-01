"""代理环境变量兼容处理。

部分开发环境会设置 ``ALL_PROXY=socks://...``，但 httpx/openai 需要明确的
``socks5://`` / ``socks4://`` 方案；若未安装 ``socksio``，使用 SOCKS 代理还会
触发 ImportError。本模块在应用启动时清理这些环境变量，避免模型初始化阶段抛出
难以定位的 ValidationError/ImportError。
"""

from __future__ import annotations

import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

_SOCKS_SCHEME_ALIASES = ("socks://", "socks4://", "socks5://", "socks5h://")


def _has_socks_support() -> bool:
    """检查是否已安装 ``socksio`` 包。"""
    return importlib.util.find_spec("socksio") is not None


def _normalize_socks_url(value: str) -> str:
    """将通用的 ``socks://`` 规范化为 ``socks5://``。"""
    if value.lower().startswith("socks://"):
        return "socks5://" + value[len("socks://") :]
    return value


def _is_socks_proxy(value: str | None) -> bool:
    """判断代理 URL 是否使用 SOCKS 系列协议。"""
    if not value:
        return False
    return value.lower().startswith(_SOCKS_SCHEME_ALIASES)


def configure_proxy_environment() -> None:
    """检查并修正代理环境变量。

    处理逻辑：
    1. ``ALL_PROXY`` / ``all_proxy`` 若使用 ``socks://``，改写为 ``socks5://``；
    2. 若环境声明了 SOCKS 代理但 ``socksio`` 未安装，则移除 SOCKS 代理变量并
       记录清晰警告，让 ``HTTP_PROXY`` / ``HTTPS_PROXY`` 生效。
    """
    socks_vars = ("ALL_PROXY", "all_proxy")
    for var in socks_vars:
        value = os.environ.get(var)
        if value is None:
            continue
        normalized = _normalize_socks_url(value)
        if normalized != value:
            logger.warning(
                "Proxy scheme '%s' is ambiguous; rewriting %s to %s",
                value,
                var,
                normalized,
            )
            os.environ[var] = normalized

    has_socks = any(_is_socks_proxy(os.environ.get(var)) for var in socks_vars)
    if has_socks and not _has_socks_support():
        logger.error(
            "SOCKS proxy is configured but 'socksio' is not installed. "
            "Run 'pip install socksio' or unset ALL_PROXY/all_proxy. "
            "Removing SOCKS proxy from environment so HTTP(S) proxies can be used."
        )
        for var in socks_vars:
            os.environ.pop(var, None)
