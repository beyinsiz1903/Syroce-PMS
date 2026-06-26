"""
Agency v1 — Atomik envanter claim/release servisi (ADR Karar 5).

Bu modul YENI bir atomik mekanizma KURMAZ; mevcut tek atomik dogruluk kaynagini
REUSE eder: `core/atomic_booking.py`. Oradaki `create_booking_atomic`:
  - her gece icin `room_night_locks`'a unique-index insert (tek atomik garanti),
  - ilk catisan gecede BookingConflictError (kismi-claim compensation: o ana
    kadar tutulan geceler geri salinir),
  - basarida booking insert + audit timeline.
room_type_inventory materialized view (5dk reconcile) SALT-OKUNUR; dogruluk
kaynagi DEGILDIR (overbooking yalnizca DB-atomik lock'tan gelir).

Bu seam'in tek isi: acente sozlesmesine cevirmek — catisma -> `InventoryConflict`
(`conflict_date` = ilk catisan gece) -> T6 bunu 409 `inventory_conflict` zarfina
esler. Iptalde DB-atomik release.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agency_v1.inventory")


class InventoryConflict(Exception):
    """Atomik claim catismasi (Karar 5). Acente 409 `inventory_conflict` kaynagi.

    `conflict_date`: ilk catisan gece (YYYY-MM-DD) veya None (bookings-seviyesi
    overlap guard'inda tekil gece olmayabilir).
    """

    def __init__(
        self,
        *,
        conflict_date: str | None,
        conflict_type: str = "booking",
        conflicting_booking_id: str | None = None,
    ):
        self.conflict_date = conflict_date
        self.conflict_type = conflict_type
        self.conflicting_booking_id = conflicting_booking_id
        super().__init__(
            f"inventory_conflict night={conflict_date} type={conflict_type}"
        )


async def claim_reservation_inventory(booking_doc: dict[str, Any]) -> dict[str, Any]:
    """Atomik cok-geceli envanter claim (Karar 5). Basari -> persist edilen
    booking dokumani. Catisma -> InventoryConflict (conflict_date = ilk catisan
    gece). Atomiklik/compensation tamamen `create_booking_atomic`'te."""
    from core.atomic_booking import BookingConflictError, create_booking_atomic

    try:
        return await create_booking_atomic(booking_doc)
    except BookingConflictError as exc:
        nights = exc.conflicting_nights or []
        conflict_date = nights[0] if nights else None
        # Catisma normal akis; PII/secret loglanmaz, yalniz tenant/oda/gece.
        logger.info(
            "agency inventory conflict tenant=%s room=%s night=%s type=%s",
            booking_doc.get("tenant_id"),
            booking_doc.get("room_id"),
            conflict_date,
            exc.conflict_type,
        )
        raise InventoryConflict(
            conflict_date=conflict_date,
            conflict_type=exc.conflict_type,
            conflicting_booking_id=exc.conflicting_booking_id,
        ) from exc


async def release_reservation_inventory(
    tenant_id: str,
    booking_id: str,
    *,
    reason: str = "cancelled",
    correlation_id: str | None = None,
) -> int:
    """Iptal/no-show'da room-night lock'larini DB-atomik salar. Salinan gece
    sayisini doner (idempotent: yoksa 0)."""
    from core.atomic_booking import release_booking_nights

    return await release_booking_nights(
        tenant_id, booking_id, reason=reason, correlation_id=correlation_id
    )
