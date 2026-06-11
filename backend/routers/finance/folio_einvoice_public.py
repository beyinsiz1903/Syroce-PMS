"""Public, token-authenticated e-Fatura data fetch for closed folios.

This is the *pull* half of the reference-based ``folio.closed.v1`` event. The SXI
event carries only identifiers + light monetary context + a signed, time-limited
URL — NEVER guest PII. External e-Fatura middleware exchanges that signed URL here
for the authoritative invoice data (folio + charges + payments + decrypted guest /
booking) under the PMS' own authority ("veri sağlayan otorite").

Auth model: there is NO JWT. Authorization is the HMAC fetch token, which binds
``(tenant_id, folio_id, stored closed_at, exp)``. The token is verified against the
folio's CURRENTLY-STORED ``closed_at`` so a reopened/reclosed folio invalidates any
previously-issued token. The path lives under ``/api/public`` and declares no
``Depends(get_current_user)`` — like the room-QR public routes, the tenant
middleware sets no context for it, so every collection read passes an explicit
``tenant_id`` filter (no cross-tenant exposure).
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Query, Request

from core.folio_close_event import (
    FetchSecretMissing,
    normalize_closed_at,
    verify_fetch_token,
)
from core.tenant_db import get_system_db, set_tenant_context

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP for the audit trail (informational only)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.get("/api/public/finance/folio/{folio_id}/einvoice-data")
async def fetch_folio_einvoice_data(
    folio_id: str,
    request: Request,
    tenant_id: str = Query(..., description="Owning tenant (bound into the token)"),
    exp: int = Query(..., description="Token expiry (unix epoch seconds)"),
    token: str = Query(..., description="HMAC-SHA256 fetch token"),
):
    """Return authoritative e-Fatura data for a closed folio against a signed token.

    - 404 when the folio does not exist, belongs to another tenant, or is not
      closed (no existence/role oracle beyond holding the exact UUID + tenant).
    - 403 ``token_expired`` / ``token_invalid`` when the signature/TTL fails.
    """
    raw = get_system_db()

    # Gating read via the RAW (unscoped) db with an explicit tenant filter — no
    # tenant context exists on this public path, so we never rely on the scoped
    # proxy here. We need the STORED closed_at to verify the token.
    folio = await raw.folios.find_one(
        {"id": folio_id, "tenant_id": tenant_id, "status": "closed"},
        {"_id": 0},
    )
    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    closed_at_norm = normalize_closed_at(folio.get("closed_at"))
    try:
        verdict = verify_fetch_token(
            token,
            tenant_id=tenant_id,
            folio_id=folio_id,
            closed_at_norm=closed_at_norm,
            exp_epoch=exp,
        )
    except FetchSecretMissing:
        # Fail-closed: no signing secret configured -> cannot verify any token.
        raise HTTPException(status_code=503, detail="signing_unavailable")
    if verdict == "expired":
        raise HTTPException(status_code=403, detail="token_expired")
    if verdict != "ok":
        raise HTTPException(status_code=403, detail="token_invalid")

    # Authorized. Set the verified tenant on the context so the scoped helpers
    # below (folio details + audit log) operate strictly within this tenant. The
    # tenant middleware's finally-block clears the context after the response.
    set_tenant_context(tenant_id)

    # Reuse the canonical folio-detail bundle (folio + charges + payments +
    # server-side balance) so this endpoint stays the single source of truth.
    from routers.finance.folio import _legacy_get_folio_details

    bundle = await _legacy_get_folio_details(tenant_id, folio_id)

    from core.database import db
    from security.encrypted_lookup import decrypt_booking_doc, decrypt_guest_doc

    guest: dict = {}
    if folio.get("guest_id"):
        guest_doc = await db.guests.find_one(
            {"id": folio["guest_id"], "tenant_id": tenant_id},
            {"_id": 0, "name": 1, "email": 1, "phone": 1, "tc_no": 1, "address": 1},
        )
        if guest_doc:
            guest = decrypt_guest_doc(guest_doc) or {}

    booking: dict = {}
    if folio.get("booking_id"):
        booking_doc = await db.bookings.find_one(
            {"id": folio["booking_id"], "tenant_id": tenant_id},
            {
                "_id": 0, "check_in": 1, "check_out": 1, "room_id": 1,
                "room_number": 1, "adults": 1, "children": 1,
            },
        )
        if booking_doc:
            booking = decrypt_booking_doc(booking_doc) or {}

    # Audit the PII disclosure with a synthetic, clearly-non-human actor.
    from core.helpers import create_audit_log

    actor = SimpleNamespace(
        id="efatura-fetch-token", name="e-Fatura Fetch Token", role="system"
    )
    await create_audit_log(
        tenant_id,
        actor,
        "folio_einvoice_fetch",
        "folio",
        folio_id,
        {"event": "folio.closed.v1", "folio_number": folio.get("folio_number")},
        _client_ip(request),
    )

    return {
        "event": "folio.closed.v1",
        "tenant_id": tenant_id,
        "fetched_at": datetime.now(UTC).isoformat(),
        "folio": bundle["folio"],
        "charges": bundle["charges"],
        "payments": bundle["payments"],
        "balance": bundle["balance"],
        "guest": guest,
        "booking": booking,
    }
