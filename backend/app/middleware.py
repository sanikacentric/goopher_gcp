"""
Abuse-protection middleware: request size limits + per-client rate limiting.

This guards the public, LLM-backed endpoints against cost-DoS (someone hammering
/chat to burn the Gemini/Vertex budget) and oversized payloads. It is dependency
-free (no Redis/library) — a sliding-window counter in process memory.

Caveat (honest): with Cloud Run autoscaling to multiple instances, each instance
keeps its own counters, so the effective limit is per-instance, not strictly
global. For a single-user locked-down service with max-instances=2 that's plenty
to stop abuse; for stricter global limits you'd back the counters with Firestore
or Memorystore/Redis. The body-size limit IS exact per request regardless.

Client identity for rate limiting, in priority order:
  1. the authenticated customer id (from a valid Bearer JWT), else
  2. the caller IP (X-Forwarded-For first hop on Cloud Run, else peer).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import get_settings
from .observability.telemetry import incr, log_event

_settings = get_settings()

# Register the abuse counters so they show up at /metrics.
for _m in ("rate_limited_total", "oversized_rejected_total"):
    incr(_m, 0)


class _SlidingWindow:
    """Per-key sliding-window request counter (timestamps in a deque)."""

    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        now = time.time()
        cutoff = now - window_s
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] < cutoff:   # drop timestamps outside the window
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            # Opportunistic cleanup so the dict doesn't grow unbounded.
            if len(self._hits) > 10000:
                self._hits.pop(next(iter(self._hits)), None)
            return True


def _client_id(request: Request) -> str:
    """Identify the caller: authenticated customer id if possible, else IP."""
    # Try to read the JWT subject without raising (best-effort identity).
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        from .auth.auth import decode_token  # local import to avoid a cycle

        claims = decode_token(auth.split(" ", 1)[1])
        if claims and claims.get("sub"):
            return f"user:{claims['sub']}"
    # Cloud Run puts the real client IP first in X-Forwarded-For.
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces request-size and per-client rate limits before the route runs."""

    def __init__(self, app):
        super().__init__(app)
        self._window = _SlidingWindow()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # --- 1) Request body size limit (cheap, always on for write methods) ---
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl:
                try:
                    if int(cl) > _settings.max_request_bytes:
                        incr("oversized_rejected_total")
                        log_event("request_too_large", path=path, content_length=cl)
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request body too large."},
                        )
                except ValueError:
                    pass

        # --- 2) Per-client rate limits (skip health/metrics/dev + static) ---
        if _settings.rate_limit_enabled and not (
            path in ("/healthz", "/metrics") or path.startswith("/dev") or _is_static(path)
        ):
            client = _client_id(request)

            # Global budget for every client.
            if not self._window.allow(
                f"{client}:global", _settings.rate_limit_global_per_min
            ):
                return self._limited(path, client, "global")

            # Tighter budget for the expensive LLM endpoint.
            if path == "/chat" and not self._window.allow(
                f"{client}:chat", _settings.rate_limit_chat_per_min
            ):
                return self._limited(path, client, "chat")

            # Brute-force protection on login.
            if path == "/auth/login" and not self._window.allow(
                f"{client}:login", _settings.rate_limit_login_per_min
            ):
                return self._limited(path, client, "login")

        return await call_next(request)

    @staticmethod
    def _limited(path: str, client: str, scope: str) -> JSONResponse:
        incr("rate_limited_total")
        log_event("rate_limited", path=path, client=client, scope=scope)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": "60"},
        )


def _is_static(path: str) -> bool:
    """The storefront's static assets shouldn't count against API rate limits."""
    return path == "/" or path.endswith((".js", ".css", ".png", ".ico", ".html", ".svg"))
