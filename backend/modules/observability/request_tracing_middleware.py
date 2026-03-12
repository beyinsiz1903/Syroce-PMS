"""
Request Tracing Middleware for FastAPI.
Real request-level observability with correlation_id propagation,
latency measurement, error capture, slow endpoint detection,
and route-level performance stats.
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("observability.middleware")

# Skip tracing for these paths (health checks, static assets)
SKIP_PATHS = {"/health", "/api/health", "/favicon.ico", "/static"}
SLOW_THRESHOLD_MS = 1000


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Production request tracing middleware.
    - Generates/propagates X-Correlation-ID
    - Measures request latency
    - Captures error responses
    - Detects slow endpoints
    - Records to observability tracing service
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip non-API / health paths
        if any(path.startswith(sp) for sp in SKIP_PATHS):
            return await call_next(request)

        # Correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Extract tenant from JWT if available (non-blocking)
        tenant_id = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                import jwt as pyjwt
                import os
                token = auth_header[7:]
                secret = os.environ.get("JWT_SECRET", "")
                if secret:
                    payload = pyjwt.decode(token, secret, algorithms=["HS256"],
                                           options={"verify_exp": False})
                    tenant_id = payload.get("tenant_id")
        except Exception:
            pass

        # Start trace
        start_time = time.time()

        try:
            from modules.observability.distributed_tracing import tracing
            trace_id = tracing.start_trace(
                request_path=path,
                method=request.method,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
        except Exception:
            trace_id = None

        # Process request
        status_code = 500
        error_msg = None
        try:
            response = await call_next(request)
            status_code = response.status_code

            # Add correlation ID to response
            response.headers["X-Correlation-ID"] = correlation_id
            return response
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
                metrics.histogram("http_request_duration_ms", elapsed_ms,
                                  {"method": request.method, "path": _normalize_path(path)})
                metrics.increment("http_requests_total",
                                  tags={"method": request.method, "status": str(status_code)})

                if is_error:
                    metrics.increment("http_errors_total",
                                      tags={"method": request.method, "path": _normalize_path(path),
                                            "status": str(status_code)})

                if is_slow:
                    metrics.increment("http_slow_requests",
                                      tags={"path": _normalize_path(path)})
            except Exception:
                pass

            # Track error in error tracker for 5xx
            if status_code >= 500 and error_msg:
                try:
                    from modules.observability.error_tracker import error_tracker
                    import asyncio
                    asyncio.create_task(error_tracker.track_error(
                        error_type="http_500",
                        message=error_msg[:300],
                        module=_normalize_path(path),
                        tenant_id=tenant_id,
                        severity="high",
                    ))
                except Exception:
                    pass

            if is_slow:
                logger.warning(f"SLOW REQUEST: {request.method} {path} took {elapsed_ms}ms")


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
