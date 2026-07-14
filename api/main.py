"""FastAPI application factory."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_error_handlers
from api.observability import ObservabilityMiddleware, configure_logging, metrics_response
from api.routes import router
from api.security import SecurityHeadersMiddleware, create_chat_rate_limiter

load_dotenv()


def configured_origins() -> list[str]:
    configured = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:4200,http://localhost:8000",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(
        title="Sole Syntax Support API",
        description="Typed API for the policy-aware customer support demo.",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(ObservabilityMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    register_error_handlers(application)
    application.include_router(router)
    application.state.chat_rate_limiter = create_chat_rate_limiter()

    application.add_api_route(
        "/internal/metrics",
        metrics_response,
        methods=["GET"],
        include_in_schema=False,
        tags=["operations"],
    )
    return application


app = create_app()
