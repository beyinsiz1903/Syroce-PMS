"""One atomic delivery -> canonical folio charge + legacy ledger projection."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from core.audit_chain import append_audit_log
from core.tenant_db import tenant_context


async def deliver_laundry(db, tenant_id, order_id, actor):
    async def transaction(session):
        kw = {"session": session}
        settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, **kw)
        order = next((row for row in (settings or {}).get("laundry_orders", []) if row.get("id") == order_id), None)
        if not order:
            raise HTTPException(404, "Sipariş bulunamadı")
        booking_id, folio_id = order.get("booking_id"), order.get("folio_id")
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, **kw)
        folio = await db.folios.find_one({"id": folio_id, "booking_id": booking_id, "tenant_id": tenant_id}, **kw)
        charge_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"syroce:laundry:{tenant_id}:{order_id}"))
        previous = await db.folio_charges.find_one({"id": charge_id, "tenant_id": tenant_id}, **kw)
        if previous and order.get("folio_charged"):
            return {"id": order_id, "status": "delivered", "folio_charge": {"charged": True, "amount": previous["total"], "entry_id": order.get("folio_entry_id"), "replayed": True}}
        if not booking or not folio or folio.get("status") != "open" or booking.get("status") not in {"checked_in", "in_house"}:
            raise HTTPException(409, "Teslim için aynı rezervasyona bağlı açık folyo ve içeride misafir gereklidir")
        if order.get("status") not in {"pending", "in_progress", "ready"}:
            raise HTTPException(409, "İptal veya tamamlanmış sipariş tekrar teslim edilemez")
        room = await db.rooms.find_one({"tenant_id": tenant_id, "room_number": order.get("room_number")}, **kw)
        if not room or (booking.get("room_id") and booking["room_id"] != room.get("id")) or (not booking.get("room_id") and booking.get("room_number") != order.get("room_number")):
            raise HTTPException(409, "Sipariş odası ve güncel konaklama eşleşmiyor; kaynak incelemesi gereklidir")
        try:
            amount = Decimal(str(order.get("total")))
            if not amount.is_finite() or amount <= 0 or amount > Decimal("1e9") or amount != amount.quantize(Decimal("0.01")):
                raise ValueError
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise HTTPException(422, "Çamaşırhane tutarı geçersiz") from exc
        currency = str(booking.get("currency") or folio.get("currency") or "TRY").upper()
        hotel = await db.hotel_settings.find_one({"tenant_id": tenant_id}, **kw) or {}
        order_currency = str(order.get("currency") or hotel.get("currency") or "TRY").upper()
        if order_currency != currency:
            raise HTTPException(409, "Çamaşırhane ve folyo para birimleri farklı; kur uydurularak teslim yapılamaz")
        day = (settings or {}).get("business_date")
        if not day:
            raise HTTPException(409, "Açık iş günü doğrulanamadı")
        closed = await db.night_audit_runs.find_one({"tenant_id": tenant_id, "business_date": day, "status": {"$in": ["completed", "completed_with_exceptions"]}}, **kw)
        if closed:
            raise HTTPException(409, "Kapanmış iş gününe çamaşırhane ücreti işlenemez")
        # Serialize sequence allocation for two different deliveries on one folio.
        await db.folios.update_one({"id": folio_id, "tenant_id": tenant_id}, {"$inc": {"laundry_post_revision": 1}}, **kw)
        key = f"laundry:{order_id}"
        ledger = await db.folio_ledger.find_one({"tenant_id": tenant_id, "folio_id": folio_id, "idempotency_key": key}, **kw)
        now = datetime.now(UTC).isoformat()
        description = "Çamaşırhane - Oda " + str(order.get("room_number") or "-") + " (" + ", ".join(f"{i.get('name', '?')} x{i.get('quantity', 1)}" for i in order.get("items", [])) + ")"
        if ledger:
            if ledger.get("business_date") != day or ledger.get("currency") != currency or ledger.get("is_voided") or Decimal(str(ledger.get("amount"))) != amount:
                raise HTTPException(409, "Önceki çamaşırhane mali kaydı güncel siparişle uyuşmuyor; kaynak incelemesi gereklidir")
        else:
            last = await db.folio_ledger.find_one({"tenant_id": tenant_id, "folio_id": folio_id}, sort=[("sequence_number", -1)], **kw)
            ledger = {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "folio_id": folio_id, "booking_id": booking_id,
                "sequence_number": (last or {}).get("sequence_number", 0) + 1, "entry_type": "charge", "amount": float(amount),
                "currency": currency, "description": description, "charge_code": "LAUNDRY", "tax_amount": 0,
                "idempotency_key": key, "posted_at": now, "posted_by": actor.email, "business_date": day, "is_voided": False,
                "metadata": {"laundry_order_id": order_id}}
            await db.folio_ledger.insert_one({**ledger}, **kw)
        charge = {"id": charge_id, "tenant_id": tenant_id, "folio_id": folio_id, "booking_id": booking_id,
            "source_ledger_entry_id": ledger["id"], "source_laundry_order_id": order_id,
            "description": ledger["description"], "charge_type": "laundry", "charge_category": "laundry",
            "quantity": 1, "amount": float(amount), "unit_price": float(amount), "total": float(amount),
            "currency": currency, "business_date": day, "posted_at": ledger["posted_at"], "posted_by": ledger["posted_by"], "voided": False}
        await db.folio_charges.update_one({"id": charge_id, "tenant_id": tenant_id}, {"$setOnInsert": charge}, upsert=True, **kw)
        await db.tenant_settings.update_one({"tenant_id": tenant_id, "laundry_orders.id": order_id}, {"$set": {
            "laundry_orders.$.status": "delivered", "laundry_orders.$.folio_charged": True,
            "laundry_orders.$.folio_entry_id": ledger["id"], "laundry_orders.$.folio_charge_id": charge_id,
            "laundry_orders.$.updated_at": now}}, **kw)
        if not previous:
            await append_audit_log(db, {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "user_id": actor.id,
                "action": "laundry_delivered", "entity_type": "laundry_order", "entity_id": order_id,
                "timestamp": now, "metadata": {"folio_id": folio_id, "charge_id": charge_id, "amount": float(amount), "currency": currency}}, session=session, require_chain=True)
        return {"id": order_id, "status": "delivered", "folio_charge": {"charged": True, "amount": float(amount), "entry_id": ledger["id"], "replayed": False}}

    with tenant_context(tenant_id):
        async with await db.client.start_session() as session:
            result = await session.with_transaction(transaction)
    return result
