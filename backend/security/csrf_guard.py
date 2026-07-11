import logging
import os
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("security.csrf_guard")

# Localhost origins are ALWAYS allowed for local development, regardless of
# the ALLOWED_ORIGINS env var (which is set for production deployments and
# would otherwise overwrite the defaults, dropping localhost:5000).
_DEV_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8001",
]
_ALWAYS_ALLOWED_ORIGINS = [
    "https://pms.syroce.com",
    "https://www.pms.syroce.com",
    "https://syroce.com",
    "https://syroce-b2b-api.syroce.com",
]
# Build the final set: dev origins + always-allowed + any extra from env var.
# The env var ADDS to the base set (not replaces), so production deployments
# that set ALLOWED_ORIGINS still keep localhost working locally.
_ENV_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: set[str] = set()
ALLOWED_ORIGINS.update(o.lower() for o in _DEV_ORIGINS)
ALLOWED_ORIGINS.update(o.lower() for o in _ALWAYS_ALLOWED_ORIGINS)
if _ENV_ORIGINS:
    ALLOWED_ORIGINS.update(o.strip().lower() for o in _ENV_ORIGINS.split(",") if o.strip())

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

    # Bypass CSRF check ONLY for Twilio's public voice webhook endpoints.
    # These endpoints use Twilio's X-Twilio-Signature cryptographic validation.
    # Cookie-based authenticated endpoints (like /api/contact-center/voice/token)
    # must remain protected under CSRF.
    TWILIO_PUBLIC_WEBHOOKS = {
        "/api/voice/inbound",
        "/api/voice/outbound",
        "/api/voice/status",
        "/api/voice/recording",
    }
    if request.url.path in TWILIO_PUBLIC_WEBHOOKS:
        return await call_next(request)

    # Bypass CSRF check for HotelRunner public webhooks.
    # These endpoints use HotelRunner's signature or token validation.
    HR_WEBHOOK_PATHS = (
        "/api/channel-manager/hotelrunner/callback",
        "/api/channel-manager/hotelrunner/webhooks/reservations",
        "/api/channel-manager/hotelrunner/webhooks/modifications",
        "/api/channel-manager/hotelrunner/webhooks/cancellations",
    )
    if request.url.path.startswith(HR_WEBHOOK_PATHS):
        return await call_next(request)


    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    if not origin and not referer:
        # Bypass origin check if we are in testing mode (pytest with default httpx client)
        if os.environ.get("TESTING") == "1":
            return await call_next(request)
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
