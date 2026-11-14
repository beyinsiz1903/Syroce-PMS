"""Atomic movement of existing receivables between open guest accounts.

No copied revenue, no moved receipts, no exchange-rate assumptions. The original
service identity, dates and tax survive a change of the responsible room.
"""
import hashlib
import json
import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException

from core.accommodation_charges import is_base_room_charge
from core.booking_atomicity import with_resource_locks
from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import currency_code, money, rounded
from modules.pms_core.reporting_financials import effective_folio_payment


async def transfer_posted_charges(database, client, tenant_id, actor_id, body):
    ids = list(body.charge_ids)
    if not body.to_folio_id or body.from_folio_id == body.to_folio_id:
        raise HTTPException(400, "Farklı bir hedef folyo seçin")
    if not ids or len(ids) > 200 or len(ids) != len(set(ids)):
        raise HTTPException(400, "1–200 farklı hizmet kalemi seçin")
    if not 3 <= len(body.reason.strip()) <= 500:
        raise HTTPException(422, "Aktarım nedeni 3–500 karakter olmalı")
    folio_ids = sorted([body.from_folio_id, body.to_folio_id])
    initial = await database.folios.find({"tenant_id": tenant_id, "id": {"$in": folio_ids}}, {"_id": 0}).to_list(2)
    if len(initial) != 2:
        raise HTTPException(404, "Folyo bulunamadı")
    booking_ids = sorted({row.get("booking_id") for row in initial if row.get("booking_id")})
    if any(not row.get("booking_id") for row in initial):
        raise HTTPException(409, "Aktarım için rezervasyona bağlı misafir folyoları seçin")
    payload = body.model_dump(mode="json", exclude={"request_id"})
    payload["charge_ids"] = sorted(ids)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    request_id = str(body.request_id or uuid.uuid5(uuid.NAMESPACE_URL, f"folio-transfer:{tenant_id}:{fingerprint}"))
    operation_key = f"folio-transfer:{tenant_id}:{request_id}"

    async def commit(session):
        previous = await database.folio_operations.find_one({"_id": operation_key, "tenant_id": tenant_id}, session=session)
        if previous:
            if previous.get("fingerprint") != fingerprint:
                raise HTTPException(409, "İşlem anahtarı farklı bir aktarım için kullanılmış")
            return previous["result"]
        folios = await database.folios.find({"tenant_id": tenant_id, "id": {"$in": folio_ids}}, {"_id": 0}, session=session).to_list(2)
        if len(folios) != 2 or any(row.get("status") != "open" for row in folios):
            raise HTTPException(409, "Kaynak ve hedef folyo açık olmalı")
        by_id = {row["id"]: row for row in folios}
        source, target = by_id[body.from_folio_id], by_id[body.to_folio_id]
        if {row.get("booking_id") for row in folios} != set(booking_ids):
            raise HTTPException(409, "Folyonun rezervasyonu değişti; ekranı yenileyin")
        bookings = await database.bookings.find({"tenant_id": tenant_id, "id": {"$in": booking_ids}}, {"_id": 0}, session=session).to_list(2)
        if len(bookings) != len(booking_ids) or any(row.get("status") in {"cancelled", "canceled", "no_show", "checked_out"} for row in bookings):
            raise HTTPException(409, "Aktif rezervasyonların açık folyolarını seçin")
        booking_map = {row["id"]: row for row in bookings}
        codes = [row.get("currency") or booking_map[row["booking_id"]].get("currency") for row in folios]
        if not all(codes) or len({currency_code(code) for code in codes}) != 1:
            raise HTTPException(409, "Folyo para birimleri aynı ve açıkça kayıtlı olmalı")
        code = currency_code(codes[0])
        if any(row.get("invoice_id") for row in folios) or await database.invoices.find_one({
            "tenant_id": tenant_id, "voided": {"$ne": True}, "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
            "$or": [{"booking_id": {"$in": booking_ids}}, {"folio_id": {"$in": folio_ids}}, {"folio_ids": {"$in": folio_ids}}],
        }, session=session):
            raise HTTPException(409, "Faturaya bağlı hesaplar önce fatura düzeltme akışında uzlaştırılmalı")
        settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "business_date": 1}, session=session)
        try:
            business_date = date.fromisoformat(str((settings or {}).get("business_date"))[:10]).isoformat()
        except ValueError:
            raise HTTPException(409, "Açık PMS iş günü doğrulanamadı") from None
        snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency=code, session=session)
        if any(any(c != code and v for c, v in snap["balance_by_currency"].items()) for snap in snapshots.values()):
            raise HTTPException(409, "Çok para birimli hesaplar önce mutabık hale getirilmeli")
        selected = [row for row in snapshots[source["id"]]["charges"] if row.get("id") in ids]
        if {row["id"] for row in selected} != set(ids):
            raise HTTPException(409, "Seçilen kalemler kaynakta yok veya iptal edilmiş; yenileyin")
        if any(row.get("invoice_id") or row.get("charge_category") == "split_adjustment" or
               currency_code(row.get("currency"), code) != code or money(row["total"]) <= 0 or
               money(row["total"]) != money(rounded(row["total"])) for row in selected):
            raise HTTPException(409, "Yalnız aynı para birimindeki pozitif, faturasız asıl hizmetler aktarılabilir")
        if any(is_base_room_charge(row) or row.get("charge_type") == "tax" or
               row.get("charge_category") in {"tax", "city_tax"} or row.get("konaklama_vergisi") for row in selected):
            # Moving a posted room row does not transfer the agreed stay price
            # or future night-audit plan. That would leave two collectible stays.
            raise HTTPException(409, "Konaklama ve konaklama vergisi için rezervasyon fiyat düzeltme akışını kullanın")
        if any(row.get("source_extra_charge_id") for row in selected):
            # Booking-scoped legacy extras are also read by reservation detail.
            # Do not move only their mirror and leave the source debt behind.
            raise HTTPException(409, "Rezervasyon ek ücretine bağlı kalemi kaynak ek ücret akışında uzlaştırın")
        if any(effective_folio_payment(row) > 0 and set(row.get("charge_ids") or []).intersection(ids)
               for row in snapshots[source["id"]]["payments"]):
            raise HTTPException(409, "İkram veya indirim uygulanmış hizmeti asıl kalem olarak aktaramazsınız")
        amount = money(rounded(sum(money(row["total"]) for row in selected)))
        before = {fid: money(snap["balance_by_currency"].get(code, 0)) for fid, snap in snapshots.items()}
        if amount > before[source["id"]] or (body.amount is not None and money(body.amount) != amount):
            raise HTTPException(409, "Aktarım tutarı kaynak hesabın açık borcuyla uyuşmuyor; yenileyin")
        now = datetime.now(UTC).isoformat()
        for row in selected:
            changed = await database.folio_charges.update_one({"tenant_id": tenant_id, "id": row["id"],
                "folio_id": source["id"], "voided": {"$ne": True}}, {"$set": {
                    "folio_id": target["id"], "booking_id": target["booking_id"],
                    "original_booking_id": row.get("original_booking_id") or source["booking_id"],
                }}, session=session)
            if changed.modified_count != 1:
                raise HTTPException(409, "Kalem eşzamanlı değişti; aktarım tamamen iptal edildi")
            await database.folio_postings.update_many({"tenant_id": tenant_id, "folio_id": source["id"],
                "$or": [{"folio_charge_id": row["id"]}, {"charge_id": row["id"]}]},
                {"$set": {"folio_id": target["id"], "booking_id": target["booking_id"]}}, session=session)
            await database.folio_postings.update_many({"tenant_id": tenant_id, "folio_id": target["id"],
                "reservation_id": source["booking_id"],
                "$or": [{"folio_charge_id": row["id"]}, {"charge_id": row["id"]}]},
                {"$set": {"reservation_id": target["booking_id"]}}, session=session)
        after = {source["id"]: before[source["id"]] - amount, target["id"]: before[target["id"]] + amount}
        for folio in folios:
            changed = await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"},
                {"$set": {"balance": rounded(after[folio["id"]])}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, "Hesap durumu değişti; aktarım iptal edildi")
        from core.booking_payment_state import refresh_booking_payment_state

        for booking_id in booking_ids:
            await refresh_booking_payment_state(database, tenant_id, booking_id, session=session, strict=True)
        result = {"id": request_id, "tenant_id": tenant_id, "operation_type": "transfer", "from_folio_id": source["id"],
            "to_folio_id": target["id"], "charge_ids": ids, "amount": float(amount), "reason": body.reason,
            "performed_by": actor_id, "performed_at": now}
        await database.folio_operations.insert_one({**result, "_id": operation_key, "fingerprint": fingerprint,
            "business_date": business_date, "currency": code, "result": result}, session=session)
        await database.pms_audit_trail.insert_one({"id": request_id, "tenant_id": tenant_id, "entity_type": "folio",
            "entity_id": source["id"], "action": "folio_cross_room_transfer", "performed_by": actor_id, "timestamp": now,
            "metadata": {"source_booking_id": source["booking_id"], "target_booking_id": target["booking_id"],
                         "target_folio_id": target["id"], "charge_ids": ids, "currency": code, "amount": float(amount),
                         "before": {k: rounded(v) for k, v in before.items()}, "after": {k: rounded(v) for k, v in after.items()}}}, session=session)
        return result

    return await with_resource_locks(client=client, db=database, tenant_id=tenant_id,
        locks_collection="reservation_financial_locks",
        resources=[*(('booking', bid) for bid in booking_ids), *(('folio', fid) for fid in folio_ids)], callback=commit)
