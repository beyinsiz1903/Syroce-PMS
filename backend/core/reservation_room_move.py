"""Atomic room assignment for the reservation-detail card (no external writes)."""
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from core.atomic_booking import _night_dates
from core.audit_chain import append_audit_log
from core.reservation_mutability import reservation_is_historical
from core.tenant_db import tenant_context


async def move_reservation_room(db, *, tenant_id, booking_id, data, actor, business_date, ensure_folio):
    """Commit physical state, stay locks, fee, history and sealed audit together.

    A reservation-card lease serializes views of ONE booking, not two different
    bookings targeting the same room. The room document and unique night locks
    are therefore also written in this transaction. Failure never frees the
    previous assignment or posts an orphan upgrade charge.
    """
    async def transaction(session):
        kw = {"session": session}
        current_day = await db.tenant_settings.update_one({"tenant_id": tenant_id, "business_date": business_date},
            {"$inc": {"room_move_revision": 1}}, **kw)
        if not current_day.matched_count:
            raise HTTPException(409, "İş günü değişti; oda değişikliğinden önce bilgileri yenileyin")
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}, **kw)
        if not booking:
            raise HTTPException(404, "Rezervasyon bulunamadı")
        if reservation_is_historical(booking, business_date) or booking.get("status") not in {"pending", "confirmed", "guaranteed", "checked_in"}:
            raise HTTPException(409, "Bu rezervasyon oda değişikliğine uygun değil")
        old_id = booking.get("room_id")
        if old_id == data.new_room_id:
            raise HTTPException(409, "Yeni oda mevcut odadan farklı olmalıdır")
        target = await db.rooms.find_one({"id": data.new_room_id, "tenant_id": tenant_id}, {"_id": 0}, **kw)
        if not target:
            raise HTTPException(404, "Yeni oda bulunamadı")
        old = await db.rooms.find_one({"id": old_id, "tenant_id": tenant_id}, {"_id": 0}, **kw) if old_id else None
        inhouse = booking["status"] == "checked_in"
        ready = {"available", "clean", "inspected"}
        if target.get("status") in {"out_of_order", "out_of_service", "maintenance"} or (
            inhouse and (target.get("status") not in ready or target.get("housekeeping_status") in {"dirty", "cleaning"} or target.get("current_booking_id"))
        ):
            raise HTTPException(409, "Hedef oda müsait veya temiz değil")
        party = booking.get("guests_count") or (booking.get("adults", 1) + booking.get("children", 0))
        if target.get("capacity") is not None and party > target["capacity"]:
            raise HTTPException(409, "Hedef odanın kapasitesi misafir sayısı için yetersiz")
        if inhouse and old and old.get("current_booking_id") not in {None, booking_id}:
            raise HTTPException(409, "Mevcut oda başka rezervasyona bağlı; önce kaynak durumunu kontrol edin")
        try:
            nights = _night_dates(booking["check_in"], booking["check_out"])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(409, "Konaklama tarihleri doğrulanamadı") from exc
        if not nights:
            raise HTTPException(409, "Konaklama tarihleri doğrulanamadı")
        others = await db.bookings.find({"tenant_id": tenant_id, "room_id": data.new_room_id,
            "id": {"$ne": booking_id}, "status": {"$nin": ["checked_out", "cancelled", "no_show"]}}, {"_id": 0}, **kw).to_list(None)
        for other in others:
            try:
                overlap = set(nights).intersection(_night_dates(other["check_in"], other["check_out"]))
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(409, "Hedef odanın mevcut tarih kaydı doğrulanamadı") from exc
            if overlap:
                raise HTTPException(409, "Hedef oda konaklama tarihlerinde başka rezervasyona ayrılmış")

        now = datetime.now(UTC).isoformat()
        # Touch the target even for future assignments to serialize concurrent
        # maintenance/physical claims without marking a future guest in-house.
        update = {"$inc": {"assignment_revision": 1}}
        if inhouse:
            update["$set"] = {"status": "occupied", "current_booking_id": booking_id}
        await db.rooms.update_one({"id": data.new_room_id, "tenant_id": tenant_id}, update, **kw)
        for night in nights:
            await db.room_night_locks.update_one({"tenant_id": tenant_id, "room_id": data.new_room_id,
                "night_date": night, "booking_id": booking_id}, {"$setOnInsert": {"lock_type": "booking", "created_at": now}}, upsert=True, **kw)
        await db.room_night_locks.delete_many({"tenant_id": tenant_id, "booking_id": booking_id, "room_id": {"$ne": data.new_room_id}}, **kw)
        await db.bookings.update_one({"id": booking_id, "tenant_id": tenant_id}, {"$set": {
            "room_id": data.new_room_id, "room_number": target.get("room_number"),
            "room_type": target.get("room_type", booking.get("room_type")), "updated_at": now}}, **kw)
        if inhouse and old:
            await db.rooms.update_one({"id": old_id, "tenant_id": tenant_id}, {"$set": {"status": "dirty", "housekeeping_status": "dirty", "current_booking_id": None}}, **kw)
        full_comp = booking.get("is_complimentary") and booking.get("complimentary_scope") == "full"
        amount = 0.0 if full_comp else round(data.extra_charge, 2)
        folio_id = None
        if data.extra_charge > 0:
            folio = await ensure_folio(tenant_id, booking, session=session)
            folio_id = folio["id"]
            await db.folio_charges.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_id,
                "booking_id": booking_id, "folio_id": folio_id, "currency": booking.get("currency") or folio.get("currency") or "TRY",
                "charge_category": "room", "charge_type": "room_upgrade",
                "description": f"Oda değişikliği fiyat farkı: {(old or {}).get('room_number', '-')} → {target.get('room_number', '-')}",
                "quantity": 1, "unit_price": amount, "amount": amount, "total": amount,
                "tax_rate": 0, "tax_amount": 0, "is_complimentary": bool(full_comp),
                "complimentary_original_amount": data.extra_charge if full_comp else None,
                "posted_at": now, "posted_by": actor.name, "business_date": business_date, "voided": False}, **kw)
        move = {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "booking_id": booking_id,
            "from_room_id": old_id, "from_room_number": (old or {}).get("room_number"),
            "to_room_id": data.new_room_id, "to_room_number": target.get("room_number"),
            "reason": data.reason.strip(), "moved_by": actor.name, "moved_at": now}
        await db.room_move_history.insert_one({**move}, **kw)
        details = {"from_room": move["from_room_number"], "to_room": move["to_room_number"],
            "reason": move["reason"], "extra_charge": amount, "currency": booking.get("currency") or "TRY"}
        await db.reservation_activity_log.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_id,
            "booking_id": booking_id, "action": "room_changed", "actor": actor.name, "details": details, "created_at": now}, **kw)
        await append_audit_log(db, {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "user_id": actor.id,
            "action": "room_changed", "entity_type": "reservation", "entity_id": booking_id,
            "timestamp": now, "metadata": details}, session=session, require_chain=True)
        return {"success": True, "move_record": move, "extra_charge": amount}, folio_id

    try:
        with tenant_context(tenant_id):
            async with await db.client.start_session() as session:
                return await session.with_transaction(transaction)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Hedef oda veya tarih başka işlem tarafından ayrıldı; listeyi yenileyin") from exc
