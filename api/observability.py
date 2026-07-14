"""Request tracing, structured logs, and Prometheus HTTP metrics."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="-",
)

HTTP_REQUESTS = Counter(
    "refundweave_http_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "refundweave_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_IN_PROGRESS = Gauge(
    "refundweave_http_requests_in_progress",
    "HTTP requests currently being served.",
    ("method",),
)

logger = logging.getLogger("refundweave.http")


class JsonFormatter(logging.Formatter):
    """Small JSON formatter with an explicit, non-sensitive field allowlist."""

    extra_fields = ("event", "method", "route", "status", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for field in self.extra_fields:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    """Enable structured application logs when requested by the environment."""
    if os.getenv("LOG_FORMAT", "text").lower() != "json":
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def _request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == REQUEST_ID_HEADER:
            candidate = value.decode("ascii", errors="ignore")
            if VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
    return str(uuid4())


def _route_label(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class ObservabilityMiddleware:
    """Pure ASGI middleware that also measures complete streaming responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        request_id = _request_id(scope)
        token = request_id_context.set(request_id)
        started = perf_counter()
        status_code = 500
        completed = False
        HTTP_IN_PROGRESS.labels(method=method).inc()

        def record_request() -> None:
            nonlocal completed
            if completed:
                return
            completed = True
            route = _route_label(scope)
            duration = perf_counter() - started
            if route != "/internal/metrics":
                HTTP_REQUESTS.labels(
                    method=method,
                    route=route,
                    status=str(status_code),
                ).inc()
                HTTP_DURATION.labels(method=method, route=route).observe(duration)
            logger.info(
                "HTTP request completed",
                extra={
                    "event": "http_request_completed",
                    "method": method,
                    "route": route,
                    "status": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

        async def send_observed(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                if not any(key.lower() == REQUEST_ID_HEADER for key, _value in headers):
                    headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            elif message["type"] == "http.response.body" and not message.get(
                "more_body",
                False,
            ):
                record_request()
            await send(message)

        try:
            await self.app(scope, receive, send_observed)
        finally:
            record_request()
            HTTP_IN_PROGRESS.labels(method=method).dec()
            request_id_context.reset(token)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
