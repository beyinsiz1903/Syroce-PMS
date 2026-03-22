"""
TI-003: Tenant Context Middleware
=================================
Extracts tenant_id from JWT in the Authorization header and sets
it in contextvars so that TenantAwareDBProxy auto-scopes all queries.

Runs BEFORE route handlers, ensuring all downstream DB operations
are tenant-isolated.
"""
import logging
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.tenant_db import set_tenant_context, clear_tenant_context

logger = logging.getLogger("core.tenant_middleware")

# Paths that don't require tenant context
_PUBLIC_PREFIXES = (
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/ws",
    "/api/uploads",
)

_AUTH_PATHS = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/register-guest",
    "/api/setup/make-super-admin",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Sets tenant context from JWT for every authenticated request.
    Skips public/auth endpoints where no JWT is available.
    """

    def __init__(self, app, jwt_secret: str, jwt_algorithm: str = "HS256"):
        super().__init__(app)
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip public/auth endpoints
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES + _AUTH_PATHS):
            return await call_next(request)

        # Extract JWT and set tenant context
        tenant_id = self._extract_tenant_id(request)
        if tenant_id:
            set_tenant_context(tenant_id)

        try:
            response = await call_next(request)
            return response
        finally:
            clear_tenant_context()

    def _extract_tenant_id(self, request: Request) -> str:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return ""

        token = auth_header[7:]  # Strip "Bearer "
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
                options={"verify_exp": False},  # Middleware only needs tenant_id; expiry checked by get_current_user
            )
            return payload.get("tenant_id", "")
        except (jwt.InvalidTokenError, jwt.DecodeError):
            return ""
