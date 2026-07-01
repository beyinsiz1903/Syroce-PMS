"""
Request Tracing Middleware for FastAPI.
Real request-level observability with correlation_id propagation,
latency measurement, error capture, slow endpoint detection,
and route-level performance stats.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid event-loop
conflicts in async test runners and improve performance.
"""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders

logger = logging.getLogger("observability.middleware")

# Skip tracing for these paths (health checks, static assets)
SKIP_PATHS = {"/health", "/api/health", "/favicon.ico", "/static"}
SLOW_THRESHOLD_MS = 1000


class RequestTracingMiddleware:
    """
    Pure ASGI request tracing middleware.
    - Generates/propagates X-Correlation-ID
    - Measures request latency
    - Captures error responses
    - Detects slow endpoints
    - Records to observability tracing service
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Skip non-API / health paths
        if any(path.startswith(sp) for sp in SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        # Correlation ID from headers
        raw_headers = scope.get("headers", [])
        correlation_id = None
        tenant_id = None
        for key, value in raw_headers:
            if key == b"x-correlation-id":
                correlation_id = value.decode("latin-1")
            elif key == b"authorization":
                try:
                    auth_val = value.decode("latin-1")
                    if auth_val.startswith("Bearer "):
                        import os

                        import jwt as pyjwt

                        token = auth_val[7:]
                        secret = os.environ.get("JWT_SECRET", "")
                        if secret:
                            # v42 Bug BH: enforce expiry — expired tokens
                            # should not annotate traces with their tenant_id.
                            payload = pyjwt.decode(token, secret, algorithms=["HS256"])
                            tenant_id = payload.get("tenant_id")
                except Exception:
                    pass

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Start trace
        start_time = time.time()
        trace_id = None
        try:
            from modules.observability.distributed_tracing import tracing

            trace_id = tracing.start_trace(
                request_path=path,
                method=method,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
        except Exception:
            pass

        # Wrap send to capture status code and add headers
        status_code = 500
        error_msg = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                headers = MutableHeaders(scope=message)
                headers.append("X-Correlation-ID", correlation_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            error_msg = str(exc)[:500]
            raise
        finally:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            is_slow = elapsed_ms > SLOW_THRESHOLD_MS
            is_error = status_code >= 400

            # End trace
            if trace_id:
                try:
                    from modules.observability.distributed_tracing import tracing

                    tracing.end_trace(trace_id, status_code=status_code, error=error_msg)
                except Exception:
                    pass

            # Record metrics
            try:
                from modules.observability.metrics_collector import metrics

                metrics.histogram("http_request_duration_ms", elapsed_ms, {"method": method, "path": _normalize_path(path)})
                metrics.increment("http_requests_total", tags={"method": method, "status": str(status_code)})

                if is_error:
                    metrics.increment("http_errors_total", tags={"method": method, "path": _normalize_path(path), "status": str(status_code)})
                if is_slow:
                    metrics.increment("http_slow_requests", tags={"path": _normalize_path(path)})
            except Exception:
                pass

            # Track error in error tracker for 5xx
            if status_code >= 500 and error_msg:
                try:
                    import asyncio

                    from modules.observability.error_tracker import error_tracker

                    asyncio.create_task(
                        error_tracker.track_error(
                            error_type="http_500",
                            message=error_msg[:300],
                            module=_normalize_path(path),
                            tenant_id=tenant_id,
                            severity="high",
                        )
                    )
                except Exception:
                    pass

            if is_slow:
                logger.warning(f"SLOW REQUEST: {method} {path} took {elapsed_ms}ms")


def _normalize_path(path: str) -> str:
    """Normalize path by replacing UUIDs and IDs with placeholders."""
    parts = path.split("/")
    normalized = []
    for part in parts:
        if len(part) == 36 and "-" in part:
            normalized.append("{id}")
        elif part.isdigit() and len(part) > 3:
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/".join(normalized)
