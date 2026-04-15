"""
Error Response Normalizer Middleware (O2 fix)

Intercepts JSON responses where the body contains {"success": false, ...}
and normalizes them into the standard FastAPI error format: {"detail": "..."}.

This ensures all API error responses follow a single consistent contract
regardless of which internal pattern the route handler used.
"""
import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class ErrorNormalizerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)

        if (
            response.status_code == 200
            and hasattr(response, "body_iterator")
            and response.headers.get("content-type", "").startswith("application/json")
        ):
            body_bytes = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    body_bytes += chunk.encode("utf-8")
                else:
                    body_bytes += chunk

            raw_headers = dict(response.headers.items())

            try:
                data = json.loads(body_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=raw_headers,
                    media_type=response.media_type,
                )

            if isinstance(data, dict) and data.get("success") is False:
                detail = (
                    data.get("error")
                    or data.get("message")
                    or data.get("detail")
                    or "Operation failed"
                )
                normalized = {"detail": detail, "success": False}
                return JSONResponse(
                    status_code=400,
                    content=normalized,
                )

            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=raw_headers,
                media_type=response.media_type,
            )

        return response
