"""Small, dependency-free protections for public API traffic."""

from __future__ import annotations

import os
from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import ApiError


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _trust_proxy_headers() -> bool:
    return os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {"1", "true", "yes"}


def client_identifier(request: Request) -> str:
    """Use the forwarded client only when the deployment trusts its proxy chain."""
    if _trust_proxy_headers():
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindowRateLimiter:
    """In-process limiter intended for one API process in this portfolio deployment."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def consume(self, key: str) -> int | None:
        """Return a retry-after value when limited, otherwise record the request."""
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            history = self._requests.setdefault(key, deque())
            while history and history[0] <= cutoff:
                history.popleft()
            if len(history) >= self.limit:
                return max(1, ceil(self.window_seconds - (now - history[0])))
            history.append(now)
        return None


def create_chat_rate_limiter() -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(
        limit=_positive_int("CHAT_RATE_LIMIT_REQUESTS", 12),
        window_seconds=_positive_int("CHAT_RATE_LIMIT_WINDOW_SECONDS", 60),
    )


async def enforce_chat_rate_limit(request: Request) -> None:
    limiter: SlidingWindowRateLimiter = request.app.state.chat_rate_limiter
    retry_after = limiter.consume(client_identifier(request))
    if retry_after is not None:
        raise ApiError(
            429,
            "chat_rate_limited",
            "Too many chat requests. Please wait a moment before trying again.",
            headers={"Retry-After": str(retry_after)},
        )


class SecurityHeadersMiddleware:
    """Set API-safe browser headers without imposing HTTPS in local development."""

    headers = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"camera=(), geolocation=(), payment=()"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _value in headers}
                headers.extend(header for header in self.headers if header[0] not in existing)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
