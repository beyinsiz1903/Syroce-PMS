"""
TI-003: Tenant Context Middleware
=================================
Extracts tenant_id from JWT in the Authorization header and sets
it in contextvars so that TenantAwareDBProxy auto-scopes all queries.

Runs BEFORE route handlers, ensuring all downstream DB operations
are tenant-isolated.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid event-loop
conflicts in async test runners and improve performance.
"""
import logging

import jwt

from core.tenant_db import clear_tenant_context, set_tenant_context

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


class TenantContextMiddleware:
    """
    Pure ASGI middleware that sets tenant context from JWT for every
    authenticated request. Skips public/auth endpoints.
    """

    def __init__(self, app, jwt_secret: str = "", jwt_algorithm: str = "HS256"):
        self.app = app
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip public/auth endpoints
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES + _AUTH_PATHS):
            await self.app(scope, receive, send)
            return

        # Extract JWT and set tenant context
        tenant_id = self._extract_tenant_id(scope.get("headers", []))
        if tenant_id:
            set_tenant_context(tenant_id)

        try:
            await self.app(scope, receive, send)
        finally:
            clear_tenant_context()

    def _extract_tenant_id(self, raw_headers: list) -> str:
        for key, value in raw_headers:
            if key == b"authorization":
                auth_header = value.decode("latin-1")
                if not auth_header.startswith("Bearer "):
                    return ""
                token = auth_header[7:]
                try:
                    payload = jwt.decode(
                        token,
                        self._jwt_secret,
                        algorithms=[self._jwt_algorithm],
                        options={"verify_exp": False},
                    )
                    return payload.get("tenant_id", "")
                except (jwt.InvalidTokenError, jwt.DecodeError):
                    return ""
        return ""
