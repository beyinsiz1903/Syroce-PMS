"""HTTP middleware + global exception handlers for Quick-ID."""
import logging
import traceback
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded

from schemas import MAX_IMAGE_BASE64_LENGTH

logger = logging.getLogger("quickid")

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {
    "/api/auth/login", "/api/auth/validate-password",
    "/api/health", "/api/docs", "/api/redoc", "/api/openapi.json",
    "/api/rate-limits", "/api/scan/ocr-status", "/api/scan/providers",
}


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "İstek limiti aşıldı. Lütfen biraz bekleyin ve tekrar deneyin.",
            "retry_after": str(exc.detail),
        },
    )


# v109 Bug DAJ: generic 500 catch-all → defense-in-depth against info disclosure.
# HTTPException + StarletteHTTPException + RequestValidationError + RateLimitExceeded
# are re-raised so FastAPI's built-in handlers run.
async def generic_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, (StarletteHTTPException, HTTPException, RequestValidationError, RateLimitExceeded)):
        raise exc
    logger.error(
        "Unhandled exception | path=%s method=%s type=%s\n%s",
        request.url.path, request.method, type(exc).__name__, traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu hatası oluştu. Lütfen daha sonra tekrar deneyin."},
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF koruması: Bearer token olmayan POST/PATCH/DELETE isteklerinde
    Origin veya Referer header'ı kontrol eder.
    JWT Bearer token kullanan istekler CSRF'den muaftır.
    """
    def __init__(self, app, cors_origins_list=None):
        super().__init__(app)
        self.cors_origins_list = cors_origins_list or []

    async def dispatch(self, request, call_next):
        if request.method in CSRF_SAFE_METHODS:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if path in CSRF_EXEMPT_PATHS:
            return await call_next(request)
        if path.startswith("/api/precheckin/"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")

        allowed_origins = set(self.cors_origins_list) if self.cors_origins_list else set()
        allowed_origins.add("http://localhost:3000")
        allowed_origins.add("http://localhost:8001")
        allowed_origins.add("http://127.0.0.1:3000")
        allowed_origins.add("http://127.0.0.1:8001")

        origin_ok = False
        if origin:
            origin_ok = any(origin.startswith(allowed.rstrip("/")) for allowed in allowed_origins if allowed and allowed != "*")
        if not origin_ok and referer:
            origin_ok = any(referer.startswith(allowed.rstrip("/")) for allowed in allowed_origins if allowed and allowed != "*")

        if not origin_ok and (origin or referer):
            logger.warning(f"⚠️ CSRF rejected: {request.method} {path} (origin: {origin})")
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF doğrulama hatası. İstek reddedildi."},
            )

        return await call_next(request)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "POST" and request.url.path in ["/api/scan"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_IMAGE_BASE64_LENGTH:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Görüntü boyutu çok büyük. Maksimum {MAX_IMAGE_BASE64_LENGTH // (1024*1024)}MB izin verilir."
                    },
                )
        return await call_next(request)
