"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scaffold.api.deps import scaffold_runtime
from scaffold.api.middleware.auth import AuthMiddleware
from scaffold.api.middleware.error_handler import ErrorHandlerMiddleware
from scaffold.api.middleware.request_id import RequestIdMiddleware
from scaffold.api.middleware.rate_limit import RateLimitMiddleware
from scaffold.api.routers import agents, health, runs, state, threads, tools
from scaffold.infra.config.app_config import get_app_config
from scaffold.infra.logging.config import configure_logging
from scaffold.infra.logging.middleware import LoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    try:
        config = get_app_config()
        configure_logging(
            level=config.log_level,
            format_type="text",
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
        logger.info("Scaffold runtime ready on %s:%d", config.gateway.host, config.gateway.port)
        yield

    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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

    # Gateway middleware (innermost first, outermost last)
    # Error handler wraps everything
    app.add_middleware(ErrorHandlerMiddleware)
    # Logging captures request/response metrics
    app.add_middleware(LoggingMiddleware)
    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=120,
        enabled=True,
    )
    # Request ID for tracing
    app.add_middleware(RequestIdMiddleware)
    # Authentication
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

    # Routers
    app.include_router(agents.router)
    app.include_router(runs.router)
    app.include_router(threads.router)
    app.include_router(state.router)
    app.include_router(tools.router)
    app.include_router(health.router)

    # Static frontend
    _web_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web")
    _web_dir = os.path.abspath(_web_dir)
    if os.path.isdir(_web_dir):
        app.mount("/static", StaticFiles(directory=os.path.join(_web_dir, "static")), name="static")

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(os.path.join(_web_dir, "index.html"))
    else:
        logger.warning("Frontend web directory not found at %s", _web_dir)

    return app


app = create_app()
