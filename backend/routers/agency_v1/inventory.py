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
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db

logger = logging.getLogger("agency_v1.inventory")


class InventoryConflict(Exception):
    """Atomik claim catismasi (Karar 5). Acente 409 `inventory_conflict` kaynagi.

    `conflict_date`: ilk catisan gece (YYYY-MM-DD) veya None (bookings-seviyesi
    overlap guard'inda tekil gece olmayabilir).
    `available`: o gece icin kalan musait oda (catismada 0; bilinmiyorsa None).
    """

    def __init__(
        self,
        *,
        conflict_date: str | None,
        conflict_type: str = "booking",
        conflicting_booking_id: str | None = None,
        available: int | None = None,
    ):
        self.conflict_date = conflict_date
        self.conflict_type = conflict_type
        self.conflicting_booking_id = conflicting_booking_id
        self.available = available
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


async def _release_claimed_locks(tenant_id: str, booking_id: str) -> int:
    """Kismi-claim compensation: bu booking icin tutulan TUM gece kilitlerini
    DB-atomik siler (booking_id ile; gece farkli fiziksel odalarda olabilir)."""
    res = await db.room_night_locks.delete_many(
        {"tenant_id": tenant_id, "booking_id": booking_id}
    )
    return res.deleted_count


async def claim_floating_inventory(booking_doc: dict[str, Any]) -> dict[str, Any]:
    """Floating (oda-tipi) atomik envanter claim — operatör onayli model (Karar 5).

    Acente oda TIPI satar; PMS atomik havuzu per-ODA (`room_night_locks` unique
    index). Bu fonksiyon her gece icin o tipte BOS bir fiziksel oday atomik
    kilitler (mevcut tek havuz -> front-desk/dolaysiz rezervasyonlarla paylasilir,
    overbooking YOK). Booking `room_id=None` (floating / pending-assignment) olarak
    persist edilir; somut fiziksel oda atamasi check-in'e / gece optimize ediciye
    ERTELENIR. Tetris/fragmentation cozumu: bir geceyi A odasi, ertesini B odasi
    karsilayabilir (rezervasyon mantiksal olarak floating); cok-geceli istek, HER
    gecede >=1 bos oda oldukca gecer. Bir gecede hic bos oda yoksa -> o gece tukendi
    -> InventoryConflict(conflict_date=o gece, available=0); o ana kadar tutulan
    geceler compensation ile serbest birakilir.

    Atomik dogruluk room_night_locks unique-index insert'inden gelir (yeniden
    yazilmaz); seim yalnizca gece-bazli secimi + compensation'i orkestre eder.
    """
    tenant_id = booking_doc.get("tenant_id")
    room_type = booking_doc.get("room_type")
    check_in = booking_doc.get("check_in") or booking_doc.get("check_in_date")
    check_out = booking_doc.get("check_out") or booking_doc.get("check_out_date")
    booking_id = booking_doc.get("id")
    correlation_id = booking_doc.get("correlation_id") or booking_id

    if not (tenant_id and room_type and check_in and check_out and booking_id):
        raise ValueError(
            "claim_floating_inventory requires tenant_id, room_type, check_in, check_out, id"
        )

    room_count = int(booking_doc.get("room_count") or 1)
    if room_count < 1:
        raise ValueError("claim_floating_inventory requires room_count >= 1")

    from core.atomic_booking import _night_dates

    nights = _night_dates(check_in, check_out)
    if not nights:
        raise ValueError("claim_floating_inventory requires check_out > check_in")

    # Aday fiziksel odalar (tek havuz kaynagi): bu tenant + tip + aktif.
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "room_type": room_type, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    candidate_ids = [r["id"] for r in rooms if r.get("id")]
    if not candidate_ids:
        # Bu tipte hic fiziksel oda yok -> ilk gece icin tukendi (fail-closed).
        raise InventoryConflict(
            conflict_date=nights[0], conflict_type="no_inventory", available=0
        )

    now_iso = datetime.now(UTC).isoformat()
    try:
        for night in nights:
            # Hizli yol: bu gece halihazirda kilitli adaylari ele. Gercek atomik
            # garanti yine de insert unique-index'tir (read-then-insert yarisina
            # karsi DuplicateKeyError'da bir sonraki adaya gecilir).
            locked = await db.room_night_locks.find(
                {
                    "tenant_id": tenant_id,
                    "room_id": {"$in": candidate_ids},
                    "night_date": night,
                },
                {"_id": 0, "room_id": 1},
            ).to_list(len(candidate_ids))
            locked_ids = {l["room_id"] for l in locked}
            free_ids = [rid for rid in candidate_ids if rid not in locked_ids]

            # Bu gece icin room_count adet FARKLI bos oda kilitle (grup floating).
            got = 0
            for rid in free_ids:
                if got >= room_count:
                    break
                try:
                    await db.room_night_locks.insert_one(
                        {
                            "tenant_id": tenant_id,
                            "room_id": rid,
                            "night_date": night,
                            "booking_id": booking_id,
                            "lock_type": "booking",
                            "allocation_source": "agency_floating",
                            "created_at": now_iso,
                        }
                    )
                    got += 1
                except DuplicateKeyError:
                    continue  # yaris: arada kapildi, sonraki adayi dene

            if got < room_count:
                logger.info(
                    "agency floating sold-out tenant=%s room_type=%s night=%s need=%d got=%d",
                    tenant_id, room_type, night, room_count, got,
                )
                # `available` = bu gece gercekten alinabilen oda sayisi (Karar 5 zarfi).
                raise InventoryConflict(
                    conflict_date=night, conflict_type="booking", available=got
                )

        # Tum geceler tutuldu -> floating booking'i persist et (room_id=None).
        doc = dict(booking_doc)
        doc["room_id"] = None
        doc.setdefault("allocation_source", "agency_floating")

        # PII alanlari field-level sifrelenir. FAIL-CLOSED (doktrin): sifreleme
        # modulu yoksa VEYA sifreleme basarisizsa booking PERSIST EDILMEZ —
        # plaintext PII ASLA yazilmaz. Hata mesaji misafir verisi TASIMAZ (PII
        # loglanmaz); outer except compensation ile tutulan geceleri geri salar.
        try:
            from security.encrypted_lookup import encrypt_booking_doc
        except ImportError as imp_err:
            raise RuntimeError(
                "PII encryption module unavailable; agency booking not saved (fail-closed)"
            ) from imp_err
        try:
            doc = encrypt_booking_doc(doc)
        except Exception as enc_err:
            raise RuntimeError(
                "PII encryption failed; agency booking not saved (fail-closed)"
            ) from enc_err

        try:
            from security.search_normalize import apply_collection_normalized_fields

            apply_collection_normalized_fields(doc, collection="bookings")
        except Exception:  # pragma: no cover - never block on search companions
            pass

        await db.bookings.insert_one(doc)
        doc.pop("_id", None)
        logger.info(
            "agency floating booking persisted id=%s tenant=%s room_type=%s nights=%d",
            booking_id, tenant_id, room_type, len(nights),
        )
        return doc

    except InventoryConflict:
        await _release_claimed_locks(tenant_id, booking_id)
        raise
    except Exception:
        # Booking insert / encryption hatasi -> tutulan geceleri geri sal.
        await _release_claimed_locks(tenant_id, booking_id)
        raise


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
