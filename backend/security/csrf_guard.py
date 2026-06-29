import logging
import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("security.csrf_guard")

_RAW_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8000,http://localhost:8001,http://localhost:3000")
ALLOWED_ORIGINS = {o.strip().lower() for o in _RAW_ORIGINS.split(",") if o.strip()}

CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

async def csrf_guard_middleware(request: Request, call_next):
    """
    State-less CSRF protection for cookie-based authentication.
    Validates the Origin or Referer header against ALLOWED_ORIGINS.
    """
    if request.method not in CSRF_PROTECTED_METHODS:
        return await call_next(request)

    # Bypass CSRF check for requests using Authorization header
    # (e.g., Exely/HotelRunner integrations, API clients)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return await call_next(request)



    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    if not origin and not referer:
        logger.warning(f"CSRF blocked: Missing Origin and Referer for {request.method} {request.url.path}")
        return JSONResponse(status_code=403, content={"detail": "CSRF verification failed: Missing Origin"})

    source_origin = None
    if origin:
        source_origin = origin.lower()
    elif referer:
        try:
            parsed_referer = urlparse(referer)
            source_origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}".lower()
        except Exception:
            pass

    if source_origin not in ALLOWED_ORIGINS:
        logger.warning(f"CSRF blocked: Invalid origin {source_origin} for {request.method} {request.url.path}")
        return JSONResponse(status_code=403, content={"detail": f"CSRF verification failed: Invalid Origin {source_origin}"})

    return await call_next(request)
