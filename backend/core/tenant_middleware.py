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
import time
import uuid
from datetime import UTC, datetime

import jwt

from common.request_context import (
    clear_request_context,
    client_ip_from_headers,
    set_request_context,
    user_agent_from_headers,
)
from core.tenant_db import clear_tenant_context, set_tenant_context

logger = logging.getLogger("core.tenant_middleware")

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SENSITIVE_READ_PREFIXES = (
    "/api/audit",
    "/api/reports",
    "/api/pms/guests",
    "/api/kvkk",
    "/api/security",
)

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

        # Extract JWT and set tenant context.  The same verified identity is
        # used after the response to create a privacy-safe, body-free audit
        # envelope for every authenticated mutation.
        identity = self._extract_identity(raw_headers)
        tenant_id = identity.get("tenant_id", "")
        if tenant_id:
            set_tenant_context(tenant_id)

        status_code = 500
        started = time.monotonic()

        async def send_with_status(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            method = str(scope.get("method") or "GET").upper()
            sensitive_read = method == "GET" and any(path.startswith(prefix) for prefix in _SENSITIVE_READ_PREFIXES)
            if tenant_id and identity.get("user_id") and (method in _MUTATION_METHODS or sensitive_read):
                await self._record_mutation(
                    scope=scope,
                    identity=identity,
                    status_code=status_code,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            clear_tenant_context()
            clear_request_context()

    def _extract_identity(self, raw_headers: list) -> dict:
        """Return verified, expiry-checked JWT identity without request data."""
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
                        token = chunk[len("access_token=") :]
                        break
        if not token:
            return {}
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=[self._jwt_algorithm])
            if payload.get("type") not in {None, "access"}:
                return {}
            return {
                "tenant_id": str(payload.get("tenant_id") or ""),
                "user_id": str(payload.get("user_id") or ""),
                "role": str(payload.get("role") or ""),
            }
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError):
            return {}

    def _extract_tenant_id(self, raw_headers: list) -> str:
        return self._extract_identity(raw_headers).get("tenant_id", "")

    async def _record_mutation(self, *, scope, identity: dict, status_code: int, duration_ms: int) -> None:
        """Persist a metadata-only audit envelope for every API mutation.

        Request bodies, query strings and response bodies are intentionally
        never read: passwords, card data, identity documents and guest notes
        therefore cannot leak into the generic audit trail.
        """
        path = str(scope.get("path") or "")
        if not path.startswith("/api/"):
            return
        try:
            from common.request_context import get_client_ip, get_user_agent
            from core.audit_chain import append_audit_log
            from core.tenant_db import get_system_db

            parts = [part for part in path.split("/") if part]
            module = parts[1] if len(parts) > 1 else "system"
            entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": identity["tenant_id"],
                "actor_id": identity["user_id"],
                "actor_role": identity.get("role") or "",
                "service_name": "http",
                "operation_name": f"{scope.get('method', 'POST').lower()}_{module}",
                "action": f"{scope.get('method', 'POST')} {path}",
                "target_type": module,
                "entity_type": module,
                "target_id": path,
                "entity_id": path,
                "result_status": "success" if status_code < 400 else "failure",
                "severity": "warning" if status_code >= 400 else "info",
                "http_method": scope.get("method"),
                "http_path": path,
                "http_status": status_code,
                "duration_ms": duration_ms,
                "ip_address": get_client_ip(),
                "user_agent": get_user_agent(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await append_audit_log(get_system_db(), entry)
        except Exception:
            # Auditing must not turn a successful hotel operation into a 500;
            # chain verification exposes any persistent write gap.
            logger.exception("generic mutation audit write failed")
