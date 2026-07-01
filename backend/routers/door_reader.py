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

from core.security import JWT_ALGORITHM, JWT_SECRET
from core.tenant_db import get_system_db
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

    import uuid

    db = get_system_db()

    async def _log_access(tenant_id: str | None, room_number: str | None, booking_id: str | None, keycard_id: str | None, guest_id: str | None, decision: str, reason: str | None = None):
        log_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id or "unknown",
            "room_number": room_number or payload.room_number,
            "booking_id": booking_id,
            "keycard_id": keycard_id,
            "guest_id": guest_id,
            "device_id": payload.device_id,
            "access_decision": decision,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await db.physical_access_logs.insert_one(log_entry)
        except Exception:
            pass

    # 1) Signature + expiry.
    try:
        claims = jwt.decode(payload.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        await _log_access(None, None, None, None, None, "denied", "expired")
        return _deny("expired")
    except jwt.InvalidTokenError:
        await _log_access(None, None, None, None, None, "denied", "invalid_token")
        return _deny("invalid_token")

    booking_id = claims.get("booking_id")
    if not booking_id:
        await _log_access(None, None, None, None, None, "denied", "invalid_token")
        return _deny("invalid_token")

    # 2) Bind the presented token to the currently-active stored key.
    key = await db.digital_keys.find_one(
        {"booking_id": booking_id, "token": payload.token, "status": "active"},
        {"_id": 0},
    )
    if not key:
        await _log_access(None, None, booking_id, None, None, "denied", "revoked")
        return _deny("revoked")

    tenant_id = key.get("tenant_id")
    guest_id = key.get("guest_id")
    room_number = key.get("room_number")
    keycard_id = key.get("id")

    # 2.5) Check if global lockdown is active for this tenant
    lockdown = await db.lockdown_state.find_one({"tenant_id": tenant_id, "status": "active"})
    if lockdown:
        await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "denied", "lockdown")
        return _deny("lockdown")

    # 3) Re-validate the booking server-side.
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "denied", "booking_not_found")
        return _deny("booking_not_found")

    if not _key_is_usable(booking):
        # Stay ended / cancelled: expire the stale key so it can never grant.
        await db.digital_keys.update_many(
            {"booking_id": booking_id, "tenant_id": tenant_id, "status": "active"},
            {"$set": {"status": "expired"}},
        )
        await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "denied", "not_in_house")
        return _deny("not_in_house")

    # 4) Optional physical-door binding.
    if payload.room_number and str(payload.room_number) != str(room_number or ""):
        await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "denied", "wrong_room")
        return _deny("wrong_room")

    # 5) Grant is an ATOMIC re-authorization (compare-and-set).
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
        await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "denied", "revoked")
        return _deny("revoked")

    await _log_access(tenant_id, room_number, booking_id, keycard_id, guest_id, "granted")
    return {
        "access": "granted",
        "booking_id": booking_id,
        "guest_id": guest_id,
        "room_number": room_number,
        "valid_until": key.get("expires_at"),
    }
