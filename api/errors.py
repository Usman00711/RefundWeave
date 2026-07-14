"""Customer-safe API error responses."""

import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from agent.config import ConfigurationError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


def error_payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message),
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content=error_payload(
                "service_unavailable",
                "The support service is temporarily unavailable.",
            ),
        )

    @app.exception_handler(ConfigurationError)
    async def handle_configuration_error(
        _request: Request,
        exc: ConfigurationError,
    ) -> JSONResponse:
        logger.error("Model configuration is unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content=error_payload(
                "model_unavailable",
                "The AI chat service is not configured.",
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected API error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal_error",
                "The request could not be completed.",
            ),
        )
