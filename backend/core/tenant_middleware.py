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

from common.request_context import (
    clear_request_context,
    client_ip_from_headers,
    set_request_context,
    user_agent_from_headers,
)
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
        raw_headers = scope.get("headers", [])

        # Capture client IP + user-agent for the audit trail on EVERY request
        # (including public/auth paths — failed logins must be attributable).
        set_request_context(
            client_ip_from_headers(raw_headers, scope.get("client")),
            user_agent_from_headers(raw_headers),
        )

        # Skip tenant scoping for public/auth endpoints, but keep the request
        # context set above so any audit write there still records IP/device.
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES + _AUTH_PATHS):
            try:
                await self.app(scope, receive, send)
            finally:
                clear_request_context()
            return

        # Extract JWT and set tenant context
        tenant_id = self._extract_tenant_id(raw_headers)
        if tenant_id:
            set_tenant_context(tenant_id)

        try:
            await self.app(scope, receive, send)
        finally:
            clear_tenant_context()
            clear_request_context()

    def _extract_tenant_id(self, raw_headers: list) -> str:
        token = None
        for key, value in raw_headers:
            if key == b"authorization":
                auth_header = value.decode("latin-1")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            elif key == b"cookie" and not token:
                cookie_header = value.decode("latin-1")
                for chunk in cookie_header.split(";"):
                    chunk = chunk.strip()
                    if chunk.startswith("access_token="):
                        token = chunk[len("access_token="):]
                        break

        if token:
            try:
                # v42 Bug BH (defense-in-depth): enforce JWT expiry here
                # too. Previously verify_exp=False meant expired tokens
                # still set tenant_context — if any route ever forgets
                # `Depends(get_current_user)`, stolen-token TTL becomes
                # infinite for tenant-scoped queries. Now expired tokens
                # silently produce no tenant context (matches behavior
                # for unsigned/tampered tokens).
                payload = jwt.decode(
                    token,
                    self._jwt_secret,
                    algorithms=[self._jwt_algorithm],
                )
                return payload.get("tenant_id", "")
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError):
                return ""
        return ""
