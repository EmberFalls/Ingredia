from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from time import monotonic, perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


logger = logging.getLogger("ingredient_intelligence.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request tracing, bounded local rate limiting, and browser safeguards."""

    def __init__(self, app, *, requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self.requests_per_minute = max(requests_per_minute, 1)
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", "").strip()[:80] or str(uuid4())
        client_key = request.client.host if request.client else "unknown"
        now = monotonic()
        bucket = self._requests[client_key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        remaining = max(self.requests_per_minute - len(bucket), 0)
        if len(bucket) >= self.requests_per_minute:
            response: Response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait briefly and try again.", "request_id": request_id},
                headers={"Retry-After": "60"},
            )
        else:
            bucket.append(now)
            remaining = max(self.requests_per_minute - len(bucket), 0)
            started = perf_counter()
            response = await call_next(request)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            logger.info(json.dumps({
                "event": "http_request", "request_id": request_id, "method": request.method,
                "path": request.url.path, "status": response.status_code, "duration_ms": duration_ms,
            }))
        response.headers["X-Request-ID"] = request_id
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self)"
        return response
