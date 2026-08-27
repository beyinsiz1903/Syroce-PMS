"""ASGI guard for reservation-detail mutations.

Human reservation-detail writes must carry the exact active per-view lease in
``X-Reservation-Lock-ID``.  Lock management endpoints and read-only requests
are excluded.  Route authentication still runs normally after this middleware;
JWT decoding here is only used to bind the presented lock to the same signed
user/tenant identity.
"""

from __future__ import annotations

import re

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.database import _raw_db
from core.reservation_edit_lock import ReservationEditLockLost, assert_reservation_edit_lock
from core.security import JWT_ALGORITHM, JWT_SECRET

LOCK_HEADER = "X-Reservation-Lock-ID"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Reservation-detail UI mutation surfaces.  The /api prefix is optional so the
# same guard works in direct-ASGI tests and behind the production API prefix.
_RESERVATION_PATHS = (
    re.compile(r"^(?:/api)?/pms/reservations/([^/]+)(?:/.*)?$"),
    re.compile(r"^(?:/api)?/frontdesk/(?:checkin|checkout)/([^/]+)(?:/.*)?$"),
)


def reservation_id_for_mutation(path: str, method: str) -> str | None:
    """Return the reservation id for a protected mutation, otherwise None."""
    if method.upper() not in _WRITE_METHODS:
        return None
    if "/edit-lock" in path:
        return None
    for pattern in _RESERVATION_PATHS:
        match = pattern.match(path)
        if match:
            return match.group(1)
    return None


def _bearer_token(request: Request) -> str | None:
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _identity_from_request(request: Request) -> tuple[str, str] | None:
    token = _bearer_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    token_type = payload.get("type")
    if token_type and token_type != "access":
        return None
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        return None
    return str(user_id), str(tenant_id)


class ReservationEditLockGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        booking_id = reservation_id_for_mutation(request.url.path, request.method)
        if not booking_id:
            return await call_next(request)

        identity = _identity_from_request(request)
        if not identity:
            # Authentication remains authoritative in the endpoint.  Returning
            # 401 here avoids leaking lock state to an unauthenticated caller.
            return JSONResponse(
                status_code=401,
                content={"detail": {"code": "NOT_AUTHENTICATED", "message": "Authentication required"}},
            )

        owner_user_id, tenant_id = identity
        lock_id = (request.headers.get(LOCK_HEADER) or "").strip()
        if not lock_id:
            return JSONResponse(
                status_code=423,
                content={
                    "detail": {
                        "code": "RESERVATION_EDIT_LOCK_REQUIRED",
                        "message": "Active reservation edit lock required",
                    }
                },
            )

        try:
            await assert_reservation_edit_lock(
                _raw_db,
                tenant_id=tenant_id,
                booking_id=booking_id,
                owner_user_id=owner_user_id,
                lock_id=lock_id,
            )
        except ReservationEditLockLost:
            return JSONResponse(
                status_code=423,
                content={
                    "detail": {
                        "code": "RESERVATION_EDIT_LOCK_LOST",
                        "message": "Reservation edit lock expired or belongs to another view",
                    }
                },
            )

        return await call_next(request)
