"""FastAPI 应用工厂。"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scaffold.api.deps import scaffold_runtime
from scaffold.api.middleware.auth import AuthMiddleware
from scaffold.api.middleware.error_handler import ErrorHandlerMiddleware
from scaffold.api.middleware.request_id import RequestIdMiddleware
from scaffold.api.middleware.rate_limit import RateLimitMiddleware
from scaffold.api.ag_ui import register_ag_ui_endpoints
from scaffold.api.routers import agents, health, state, threads, tools
from scaffold.core.agents import create_agent
from scaffold.infra.config.app_config import get_app_config
from scaffold.infra.logging.config import configure_logging
from scaffold.infra.logging.middleware import LoggingMiddleware
from scaffold.infra.proxy import configure_proxy_environment

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期处理器。"""
    configure_proxy_environment()
    try:
        config = get_app_config()
        configure_logging(
            level=config.log_level,
            format_type=config.log_format,
            log_dir="logs",
        )
        logger.info(
            "Configuration loaded — %d model(s), %d tool(s), %d middleware",
            len(config.models),
            len(config.tools),
            len(config.middleware.get_enabled()) if hasattr(config, "middleware") else 0,
        )
    except Exception as exc:
        logger.exception("Failed to load configuration: %s", exc)
        raise RuntimeError(f"Configuration error: {exc}") from exc

    async with scaffold_runtime(app):
        try:
            # 为每个 harness profile 注册一个独立 Agent，名称与 profile 名一致
            config = get_app_config()
            profiles = config.profiles.harness
            if not profiles:
                create_agent(name="default", checkpointer=app.state.checkpointer)
            else:
                for profile in profiles:
                    create_agent(
                        name=profile.name,
                        harness_profile=profile.name,
                        checkpointer=app.state.checkpointer,
                    )
        except Exception as exc:
            logger.exception("Failed to create agents: %s", exc)
            raise RuntimeError(f"Failed to create agents: {exc}") from exc

        # AG-UI 端点：必须在 agent 创建后注册
        register_ag_ui_endpoints(app)

        logger.info("Scaffold runtime ready on %s:%d", config.gateway.host, config.gateway.port)
        yield

    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    config = get_app_config()
    docs_url = "/docs" if config.gateway.enable_docs else None
    redoc_url = "/redoc" if config.gateway.enable_docs else None

    app = FastAPI(
        title="DeepAgents Scaffold",
        description="Multi-agent API Gateway built on DeepAgents + Deer-Flow infrastructure",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    # Gateway 中间件（最内层先添加，最外层后添加）
    # Error handler 包裹所有中间件
    app.add_middleware(ErrorHandlerMiddleware)
    # Logging 记录请求/响应指标
    app.add_middleware(LoggingMiddleware)
    # 限流
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=120,
        enabled=True,
    )
    # Request ID 用于链路追踪
    app.add_middleware(RequestIdMiddleware)
    # 认证
    app.add_middleware(
        AuthMiddleware,
        api_key=os.getenv("SCAFFOLD_API_KEY"),
        enabled=os.getenv("SCAFFOLD_API_KEY") is not None,
    )
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由
    app.include_router(agents.router)
    app.include_router(threads.router)
    app.include_router(state.router)
    app.include_router(tools.router)
    app.include_router(health.router)

    return app


app = create_app()
