"""Lightweight in-memory sliding-window rate limiter (per client IP).

Applies to POST /api/v1/auth/* (credential brute force). No external store: set
RATE_LIMIT_ENABLED=false to disable entirely (tests, local dev).
Old buckets are swept opportunistically, piggybacked on request handling.
"""

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

WINDOW_SECONDS = 60.0
_SWEEP_EVERY_SECONDS = 60.0

# (method, path match, exact) — exact=True means full-path equality
_LIMITED_ROUTES = (
    ("POST", "/api/v1/auth/", False),
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    @staticmethod
    def _client_ip(request: Request) -> str:
        # X-Forwarded-For is client-controlled; honoring it by default lets an
        # attacker rotate buckets per request. Only trust it behind a proxy
        # that overwrites it (TRUST_PROXY_HEADERS=true).
        if get_settings().TRUST_PROXY_HEADERS:
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < _SWEEP_EVERY_SECONDS:
            return
        self._last_sweep = now
        stale = [k for k, v in self._buckets.items() if not v or v[-1] < now - WINDOW_SECONDS]
        for k in stale:
            self._buckets.pop(k, None)

    @staticmethod
    def _match(request: Request) -> str | None:
        """Return the matched route key (prefix) or None if not limited."""
        path = request.url.path
        for method, prefix, exact in _LIMITED_ROUTES:
            if request.method != method:
                continue
            if path == prefix or (not exact and path.startswith(prefix)):
                return prefix
        return None

    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        if not s.RATE_LIMIT_ENABLED:
            return await call_next(request)
        route = self._match(request)
        if route is None:
            return await call_next(request)

        now = time.monotonic()
        self._sweep(now)
        key = f"{route}:{self._client_ip(request)}"
        hits = self._buckets[key]
        while hits and hits[0] < now - WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= s.RATE_LIMIT_AUTH_PER_MINUTE:
            retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests — retry later",
                    },
                    "request_id": getattr(request.state, "request_id", "-"),
                },
            )
        hits.append(now)
        return await call_next(request)
