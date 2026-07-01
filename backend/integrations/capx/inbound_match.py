"""CapX inbound match.created / match.cancelled handler.

Spec referansı: PMS_INCELEME_RAPORU.md §4-5 (CapX → PMS Inbound Webhook).

Yön (`direction` payload alanı):
  - incoming → bu otele misafir geliyor → bookings koleksiyonunda
    yeni rezervasyon oluştur (channel="capx", origin="capx").
  - outgoing → bu otel misafiri karşı otele yolluyor → log only
    (capx_outgoing_transfers koleksiyonu).

Cancel:
  - incoming → mevcut rezervasyonu (capx_match_id ile bul) iptal et.
  - outgoing → outgoing_transfers kaydını cancelled olarak işaretle.

Tenant-isolation: tüm yazımlar gelen tenant_id'ye scoped.
Idempotency: capx_match_id koleksiyon-bazında benzersiz arandığı için
duplicate match.created tek kayıt üretir; capx_events tablosundaki
event_id idempotency'si zaten webhook'un üst katmanında çalışır.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.pms.reservations.services.reservation_service import (
    ReservationService,
)

logger = logging.getLogger(__name__)

OUTGOING_COLLECTION = "capx_outgoing_transfers"


def _parse_iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _extract_match(payload: dict[str, Any]) -> dict[str, Any]:
    m = payload.get("match")
    if not isinstance(m, dict):
        raise ValueError("payload.match missing or not an object")
    if not m.get("id"):
        raise ValueError("payload.match.id missing")
    if m.get("direction") not in ("incoming", "outgoing"):
        raise ValueError(f"invalid direction: {m.get('direction')!r}")
    return m


async def _find_existing_booking_by_match(
    tenant_id: str,
    capx_match_id: str,
) -> dict[str, Any] | None:
    return await db.bookings.find_one(
        {"tenant_id": tenant_id, "capx_match_id": capx_match_id},
        {"_id": 0},
    )


async def _find_existing_outgoing(
    tenant_id: str,
    capx_match_id: str,
) -> dict[str, Any] | None:
    return await db[OUTGOING_COLLECTION].find_one(
        {"tenant_id": tenant_id, "capx_match_id": capx_match_id},
        {"_id": 0},
    )


def _booking_payload_from_match(match: dict[str, Any]) -> dict[str, Any]:
    """Map CapX match → bookings koleksiyonu alanları.

    capacity_label genellikle DBL/SGL/TRP; pax → adults. Oda ataması yapılmaz
    (room_id boş bırakılır), front-desk daha sonra atayacak.
    """
    listing = match.get("listing") or {}
    counter = match.get("counterparty_hotel") or {}
    pax = int(listing.get("pax") or 1)
    nights = int(listing.get("nights") or 1)
    price_max = listing.get("price_max")
    price_min = listing.get("price_min")
    total = price_max if price_max is not None else price_min

    guest_name = counter.get("contact_person") or counter.get("name") or "CapX Misafir"

    return {
        # CapX'ten gelen referans alanları (cancel sırasında lookup için)
        "capx_match_id": match["id"],
        "capx_reference_code": match.get("reference_code"),
        "capx_direction": "incoming",
        # Rezervasyon temel alanları
        "guest_name": guest_name,
        "guest_id": None,
        "room_id": None,
        "room_number": None,
        "room_type": listing.get("capacity_label") or listing.get("concept") or "STD",
        "check_in": _parse_iso(listing.get("date_start")),
        "check_out": _parse_iso(listing.get("date_end")),
        "nights": nights,
        "adults": pax,
        "children": 0,
        "children_ages": [],
        "guests_count": pax,
        "total_amount": total,
        "base_rate": price_min,
        "paid_amount": 0,
        "currency": match.get("currency", "TRY"),
        "rate_plan": "CapX-B2B",
        # Channel / origin
        "channel": "capx",
        "source_channel": "capx",
        "origin": "capx",
        "allocation_source": "capx",
        "hold_status": "none",
        "special_requests": (f"CapX eşleşme: {match.get('reference_code') or match['id']} — kontak: {counter.get('phone') or '-'}"),
        "status": "confirmed",
        # Counterparty bilgisi (raporlama için)
        "capx_counterparty": {
            "id": counter.get("id"),
            "name": counter.get("name"),
            "region": counter.get("region"),
            "phone": counter.get("phone"),
            "contact_person": counter.get("contact_person"),
        },
    }


async def handle_match_created(
    *,
    tenant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    match = _extract_match(payload)
    direction = match["direction"]
    capx_match_id = match["id"]

    if direction == "incoming":
        existing = await _find_existing_booking_by_match(tenant_id, capx_match_id)
        if existing:
            return {
                "handled": True,
                "action": "noop_existing_booking",
                "direction": direction,
                "booking_id": existing.get("id"),
                "capx_match_id": capx_match_id,
            }
        booking_data = _booking_payload_from_match(match)
        try:
            booking = await ReservationService.create_reservation(tenant_id, booking_data)
        except Exception as exc:
            logger.exception(
                "match.created incoming reservation insert failed: %s",
                exc,
            )
            return {"handled": False, "error": str(exc), "capx_match_id": capx_match_id}

        logger.info(
            "CapX match.created → booking opened: tenant=%s match=%s booking=%s",
            (tenant_id or "")[:8],
            capx_match_id[:12],
            booking.get("id", "?")[:12],
        )
        return {
            "handled": True,
            "action": "booking_created",
            "direction": direction,
            "booking_id": booking.get("id"),
            "capx_match_id": capx_match_id,
        }

    # outgoing → log only
    existing = await _find_existing_outgoing(tenant_id, capx_match_id)
    if existing:
        return {
            "handled": True,
            "action": "noop_existing_outgoing",
            "direction": direction,
            "capx_match_id": capx_match_id,
        }

    listing = match.get("listing") or {}
    counter = match.get("counterparty_hotel") or {}
    transfer_doc = {
        "tenant_id": tenant_id,
        "capx_match_id": capx_match_id,
        "capx_reference_code": match.get("reference_code"),
        "status": "active",
        "currency": match.get("currency", "TRY"),
        "fee_amount": match.get("fee_amount", 0),
        "accepted_at": _parse_iso(match.get("accepted_at")),
        "cancelled_at": None,
        "cancel_reason": None,
        "counterparty_hotel": counter,
        "listing": {
            "concept": listing.get("concept"),
            "region": listing.get("region"),
            "micro_location": listing.get("micro_location"),
            "date_start": _parse_iso(listing.get("date_start")),
            "date_end": _parse_iso(listing.get("date_end")),
            "nights": listing.get("nights"),
            "pax": listing.get("pax"),
            "capacity_label": listing.get("capacity_label"),
            "price_min": listing.get("price_min"),
            "price_max": listing.get("price_max"),
        },
        "created_at": datetime.now(UTC),
    }
    try:
        await db[OUTGOING_COLLECTION].insert_one(transfer_doc)
    except Exception as exc:
        logger.exception("outgoing transfer log insert failed: %s", exc)
        return {"handled": False, "error": str(exc), "capx_match_id": capx_match_id}

    logger.info(
        "CapX match.created → outgoing transfer logged: tenant=%s match=%s",
        (tenant_id or "")[:8],
        capx_match_id[:12],
    )
    return {
        "handled": True,
        "action": "outgoing_logged",
        "direction": direction,
        "capx_match_id": capx_match_id,
    }


async def handle_match_cancelled(
    *,
    tenant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    match = _extract_match(payload)
    direction = match["direction"]
    capx_match_id = match["id"]
    cancel_reason = match.get("cancel_reason") or "CapX iptali"
    cancelled_at = _parse_iso(match.get("cancelled_at")) or datetime.now(UTC).isoformat()

    if direction == "incoming":
        existing = await _find_existing_booking_by_match(tenant_id, capx_match_id)
        if not existing:
            logger.warning(
                "match.cancelled incoming: no local booking for match=%s tenant=%s",
                capx_match_id[:12],
                (tenant_id or "")[:8],
            )
            return {
                "handled": True,
                "action": "noop_no_booking",
                "direction": direction,
                "capx_match_id": capx_match_id,
            }
        status = (existing.get("status") or "").lower()
        if status in ("cancelled", "checked_in", "checked_out", "no_show"):
            return {
                "handled": True,
                "action": "noop_terminal_status",
                "direction": direction,
                "booking_id": existing.get("id"),
                "current_status": status,
                "capx_match_id": capx_match_id,
            }
        try:
            await ReservationService.cancel_reservation(
                tenant_id,
                existing["id"],
                reason=f"CapX: {cancel_reason}",
            )
        except Exception as exc:
            logger.exception("match.cancelled cancel_reservation failed: %s", exc)
            return {"handled": False, "error": str(exc), "capx_match_id": capx_match_id}

        logger.info(
            "CapX match.cancelled → booking cancelled: tenant=%s match=%s booking=%s",
            (tenant_id or "")[:8],
            capx_match_id[:12],
            existing["id"][:12],
        )
        return {
            "handled": True,
            "action": "booking_cancelled",
            "direction": direction,
            "booking_id": existing["id"],
            "capx_match_id": capx_match_id,
        }

    # outgoing
    res = await db[OUTGOING_COLLECTION].update_one(
        {"tenant_id": tenant_id, "capx_match_id": capx_match_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": cancelled_at,
                "cancel_reason": cancel_reason,
            }
        },
    )
    return {
        "handled": True,
        "action": "outgoing_cancelled" if res.modified_count else "noop_no_outgoing",
        "direction": direction,
        "capx_match_id": capx_match_id,
    }
