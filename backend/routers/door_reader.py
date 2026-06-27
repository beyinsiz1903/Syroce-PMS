"""Door-reader verification endpoint (internal, hardware-agnostic).

A physical door reader scans the guest's digital-key QR (a signed JWT) and asks
the server whether to open the lock. The server is the SOLE authority: the
plaintext QR is never trusted. We verify the JWT signature + expiry, bind the
token to the *currently active* stored key (so a refreshed/rotated/revoked
token is rejected even when its signature is still cryptographically valid),
resolve the tenant from the stored key (never from client input), and re-check
the booking is in-house server-side. Every failure path is fail-closed
(``access: denied``). No guest PII (name / e-mail) is ever returned.

The request/response contract is deliberately vendor-neutral (a grant/deny
decision plus opaque references) so a thin per-vendor adapter (VingCard, Salto,
Assa Abloy, ...) can wrap it later without touching this verification core.
"""

import hmac
import logging
import os
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import JWT_ALGORITHM, JWT_SECRET
from domains.guest.operations_router import _key_is_usable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Door Reader"])


def _require_door_reader_auth(provided: str | None) -> None:
    """Authenticate the door-reader caller via a shared service key.

    Fail-closed: the endpoint refuses to operate unless ``DOOR_READER_SERVICE_KEY``
    is configured (no hardcoded fallback, per threat model). Comparison is
    constant-time to avoid a timing oracle.
    """
    expected = (os.environ.get("DOOR_READER_SERVICE_KEY") or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Door reader service not configured")
    candidate = (provided or "").strip()
    if not candidate or not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class DoorReaderVerifyRequest(BaseModel):
    """Vendor-neutral verification request from a door reader."""

    token: str = Field(..., min_length=1, max_length=4096, description="Scanned QR token (signed JWT)")
    device_id: str | None = Field(default=None, max_length=128, description="Reader identifier (audit only)")
    room_number: str | None = Field(default=None, max_length=64, description="Room the reader guards; if set, must match the key")


def _deny(reason: str) -> dict:
    return {"access": "denied", "reason": reason}


@router.post("/internal/door-reader/verify")
async def verify_door_reader(
    payload: DoorReaderVerifyRequest,
    x_door_reader_key: str | None = Header(default=None, alias="X-Door-Reader-Key"),
):
    """Verify a scanned digital-key token and return an open/deny decision."""
    _require_door_reader_auth(x_door_reader_key)

    # 1) Signature + expiry. ExpiredSignatureError is a subclass of
    #    InvalidTokenError, so it must be caught first.
    try:
        claims = jwt.decode(payload.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return _deny("expired")
    except jwt.InvalidTokenError:
        return _deny("invalid_token")

    booking_id = claims.get("booking_id")
    if not booking_id:
        return _deny("invalid_token")

    # 2) Bind the presented token to the currently-active stored key. A token
    #    that was rotated/refreshed maps to a non-active row -> revoked, even
    #    though its JWT signature may still be valid.
    key = await db.digital_keys.find_one(
        {"booking_id": booking_id, "token": payload.token, "status": "active"},
        {"_id": 0},
    )
    if not key:
        return _deny("revoked")

    tenant_id = key.get("tenant_id")

    # 3) Re-validate the booking server-side. Tenant is taken from the stored
    #    key, never from client input.
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not booking:
        return _deny("booking_not_found")

    if not _key_is_usable(booking):
        # Stay ended / cancelled: expire the stale key so it can never grant.
        await db.digital_keys.update_many(
            {"booking_id": booking_id, "tenant_id": tenant_id, "status": "active"},
            {"$set": {"status": "expired"}},
        )
        return _deny("not_in_house")

    # 4) Optional physical-door binding: a key for room 101 must not open 102.
    if payload.room_number and str(payload.room_number) != str(key.get("room_number") or ""):
        return _deny("wrong_room")

    # 5) Grant is an ATOMIC re-authorization (compare-and-set): the same update
    #    that records the audit trail also re-asserts the key is still active. If
    #    a concurrent refresh/rotation expired it between the read above and now,
    #    matched_count is 0 -> deny (closes the revocation race; a just-rotated
    #    token can never open the door even in the timing window).
    res = await db.digital_keys.update_one(
        {
            "booking_id": booking_id,
            "tenant_id": tenant_id,
            "token": payload.token,
            "status": "active",
        },
        {"$set": {"last_used": datetime.now(UTC).isoformat(), "last_device_id": payload.device_id}},
    )
    if getattr(res, "matched_count", 0) != 1:
        return _deny("revoked")

    return {
        "access": "granted",
        "booking_id": booking_id,
        "guest_id": key.get("guest_id"),
        "room_number": key.get("room_number"),
        "valid_until": key.get("expires_at"),
    }
