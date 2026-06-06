"""ASGI middlewares: request id + structured access log."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds an ``X-Request-Id`` header in/out and emits one access-log
    line per request with method, path, status, latency, and request id."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            log.exception(
                "rid=%s %s %s -> 500 in %.0fms",
                rid, request.method, request.url.path, elapsed,
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = rid

        if request.url.path not in ("/health", "/"):
            log.info(
                "rid=%s %s %s -> %d in %.0fms",
                rid, request.method, request.url.path, response.status_code, elapsed,
            )
        return response
