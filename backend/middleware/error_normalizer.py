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

        if response.status_code == 200 and hasattr(response, "body_iterator") and response.headers.get("content-type", "").startswith("application/json"):
            body_bytes = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    body_bytes += chunk.encode("utf-8")
                else:
                    body_bytes += chunk

            # Preserve all raw headers, but let Starlette handle content-length
            # for the reconstructed responses.
            original_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"content-length"]

            try:
                data = json.loads(body_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                fallback_resp = Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    media_type=response.media_type,
                )
                # Replace headers, ensuring we keep the new content-length
                new_cl = [h for h in fallback_resp.raw_headers if h[0].lower() == b"content-length"]
                fallback_resp.raw_headers = original_headers + new_cl
                return fallback_resp

            if isinstance(data, dict) and data.get("success") is False:
                detail = data.get("error") or data.get("message") or data.get("detail") or "Operation failed"
                normalized = {"detail": detail, "success": False}
                error_resp = JSONResponse(
                    status_code=400,
                    content=normalized,
                )
                # Keep original headers except content-type, content-length
                filtered_headers = [(k, v) for k, v in original_headers if k.lower() != b"content-type"]
                new_cl = [h for h in error_resp.raw_headers if h[0].lower() in (b"content-length", b"content-type")]
                error_resp.raw_headers = filtered_headers + new_cl
                return error_resp

            success_resp = Response(
                content=body_bytes,
                status_code=response.status_code,
                media_type=response.media_type,
            )
            new_cl = [h for h in success_resp.raw_headers if h[0].lower() == b"content-length"]
            success_resp.raw_headers = original_headers + new_cl
            return success_resp

        return response
