"""Complete room revenue before a reservation folio is closed.

Night audit normally posts one room charge per night.  A payment may however
cover the confirmed stay before the final nightly posting.  At checkout that
last amount must become a durable folio charge; otherwise the folio appears
to carry a credit even though the reservation is settled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import uuid4

_CENT = Decimal("0.01")


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value or 0))
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0")
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP) if amount.is_finite() else Decimal("0")


async def reconcile_unposted_room_charge(
    database,
    *,
    tenant_id: str,
    booking: dict[str, Any],
    posted_by: str,
    allow_closed_folio: bool = False,
    session=None,
) -> dict[str, Any]:
    """Post the remaining confirmed room amount once, then return its result.

    The idempotency key is persisted on the charge itself.  It makes retries
    and overlapping checkout requests harmless without ever mutating an
    already-posted room night.
    """
    booking_id = str(booking.get("id") or "")
    if not booking_id:
        raise ValueError("Booking id is required for room-charge reconciliation")
    confirmed_room_total = _money(booking.get("total_amount"))
    # Operational checkouts without a confirmed accommodation amount (for
    # example room-only safety tests and zero-rate stays) have nothing to
    # reconcile.  Return before touching legacy folio collections.
    if confirmed_room_total <= Decimal("0.01"):
        return {"posted": False, "idempotent": False, "charge_id": None, "amount": 0.0}

    query_kwargs = {"session": session} if session is not None else {}
    charges = await database.folio_charges.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0},
        **query_kwargs,
    ).to_list(10_000)

    idempotency_key = f"checkout-room-reconciliation:{tenant_id}:{booking_id}"
    existing = next(
        (charge for charge in charges if charge.get("idempotency_key") == idempotency_key and not charge.get("voided")),
        None,
    )
    if existing:
        return {
            "posted": False,
            "idempotent": True,
            "charge_id": existing.get("id"),
            "amount": float(_money(existing.get("total", existing.get("amount")))),
        }

    active_room_charges = [
        charge for charge in charges
        if not charge.get("voided")
        and (charge.get("charge_type") == "room_charge" or charge.get("charge_category") == "room")
    ]
    posted_room_total = sum(
        (_money(charge.get("total", charge.get("amount"))) for charge in active_room_charges),
        start=Decimal("0"),
    )
    missing_total = confirmed_room_total - posted_room_total
    if missing_total <= Decimal("0.01"):
        return {"posted": False, "idempotent": False, "charge_id": None, "amount": 0.0}

    folio_filter = {"tenant_id": tenant_id, "booking_id": booking_id, "status": "open"}
    folio = await database.folios.find_one(folio_filter, {"_id": 0}, **query_kwargs)
    if not folio:
        # Some legacy adapters do not implement find_one consistently for an
        # open-folio query.  The same bounded lookup remains tenant-scoped and
        # provides a safe compatibility fallback.
        candidates = await database.folios.find(folio_filter, {"_id": 0}, **query_kwargs).to_list(1)
        folio = candidates[0] if candidates else None
    if not folio and allow_closed_folio:
        folio = await database.folios.find_one(
            {"tenant_id": tenant_id, "booking_id": booking_id},
            {"_id": 0},
            sort=[("closed_at", -1), ("created_at", -1)],
            **query_kwargs,
        )
    if not folio:
        raise ValueError("Open folio is required to complete pending room revenue")

    posted_tax = sum((_money(charge.get("tax_amount")) for charge in active_room_charges), start=Decimal("0"))
    effective_tax_rate = posted_tax / posted_room_total if posted_room_total > 0 else Decimal("0")
    tax_amount = (missing_total * effective_tax_rate).quantize(_CENT, rounding=ROUND_HALF_UP)
    net_amount = missing_total - tax_amount
    now = datetime.now(UTC).isoformat()
    charge = {
        "id": str(uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "folio_id": folio["id"],
        "charge_type": "room_charge",
        "charge_category": "room",
        "source": "checkout_room_reconciliation",
        "idempotency_key": idempotency_key,
        "description": "Konaklama tahakkuk tamamlama",
        "date": str(booking.get("check_out") or now)[:10],
        "business_date": str(booking.get("check_out") or now)[:10],
        "quantity": 1,
        "unit_price": float(net_amount),
        "amount": float(net_amount),
        "tax_amount": float(tax_amount),
        "total": float(missing_total),
        "tax_inclusive": True,
        "voided": False,
        "posted_by": posted_by,
        "created_at": now,
    }
    await database.folio_charges.insert_one(charge, **query_kwargs)

    payments = await database.payments.find(
        {"tenant_id": tenant_id, "booking_id": booking_id, "voided": False},
        {"_id": 0, "amount": 1},
        **query_kwargs,
    ).to_list(10_000)
    active_charge_total = sum(
        (_money(item.get("total", item.get("amount"))) for item in charges if not item.get("voided")),
        start=Decimal("0"),
    ) + missing_total
    payment_total = sum((_money(payment.get("amount")) for payment in payments), start=Decimal("0"))
    await database.folios.update_one(
        {"id": folio["id"], "tenant_id": tenant_id},
        {"$set": {"balance": float(active_charge_total - payment_total)}},
        **query_kwargs,
    )
    return {"posted": True, "idempotent": False, "charge_id": charge["id"], "amount": float(missing_total)}
