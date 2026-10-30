"""Atomic, source-owned department receivables (not integration stubs).

Legacy embedded charges/posting rows remain evidence. Reconciliation creates
one canonical charge on the current open day, never guesses tax/FX, and
recalculates balances from the ledger rather than incrementing cached money.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.audit_chain import append_audit_log
from core.booking_atomicity import with_resource_locks
from core.booking_payment_state import refresh_booking_payment_state
from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from shared_kernel.audit_helper import build_audit_entry


def money(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value > Decimal("1e9") or value != value.quantize(Decimal(".01")):
            raise ValueError
        return value
    except (ValueError, InvalidOperation, TypeError):
        raise HTTPException(409, "Hizmet tutarı geçersiz; kaynak incelemesi gereklidir") from None


async def post_source_charge(db, tenant_id, source, actor_id, *, session):
    bid, kind, sid = source["booking_id"], source["kind"], source["id"]
    source_field = {"concierge": "source_concierge_request_id", "mice": "source_mice_event_id", "transfer": "source_transport_booking_id", "parking": "source_transport_booking_id"}[kind]
    booking = await db.bookings.find_one({"tenant_id": tenant_id, "id": bid}, session=session)
    if not booking:
        raise HTTPException(404, "Aynı tesiste bağlı rezervasyon bulunamadı")
    if booking.get("status") not in {"checked_in", "in_house", "confirmed", "guaranteed"} or booking.get("folio_merged_to"):
        raise HTTPException(409, "Bu konaklamaya hizmet ücreti işlenemez")
    folio = await select_booking_folio(db, tenant_id, bid, source.get("folio_id"), session=session)
    if not folio:
        raise HTTPException(409, "Hizmet için açık folyo seçilmelidir")
    code = str(source["currency"]).upper()
    if code != str(booking.get("currency") or "").upper() or code != str(folio.get("currency") or "").upper():
        raise HTTPException(409, "Hizmet, rezervasyon ve folyo para birimleri farklı")
    gross = money(source["gross"])
    tax = money(source["tax"]) if source.get("tax") is not None else None
    if tax is not None and tax > gross:
        raise HTTPException(409, "Kaynak vergi tutarı toplamdan büyük")
    full_comp = booking.get("is_complimentary") and booking.get("complimentary_scope") == "full"
    original = gross
    if full_comp:
        gross, tax = Decimal(0), Decimal(0) if tax is not None else None
    fingerprint = hashlib.sha256(json.dumps({**source, "folio_id": folio["id"]}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    cid = str(uuid5(NAMESPACE_URL, f"syroce:department:{kind}:{tenant_id}:{sid}"))
    source_query = {"$or": [{source_field: sid}, {"mice_event_id": sid}]} if kind == "mice" else {source_field: sid}
    prior = await db.folio_charges.find_one({"tenant_id": tenant_id, **source_query}, session=session)
    if prior:
        if (prior.get("id"), prior.get("source_fingerprint"), prior.get("booking_id"), prior.get("folio_id"), prior.get("currency"), prior.get("total"), bool(prior.get("voided"))) != (
            cid,
            fingerprint,
            bid,
            folio["id"],
            code,
            float(gross),
            False,
        ):
            raise HTTPException(409, "Önceki hizmet ücreti kaynakla uyuşmuyor; tekrar ücret yazılmadı")
        return {"charge": prior, "replayed": True}
    if kind == "concierge":
        for legacy in folio.get("charges", []):
            if legacy.get("concierge_request_id") == sid and (money(legacy.get("amount")) != original or legacy.get("currency") != code):
                raise HTTPException(409, "Eski concierge kaydı kaynakla uyuşmuyor")
    state = await db.tenant_settings.find_one({"tenant_id": tenant_id}, session=session) or {}
    day = state.get("business_date")
    try:
        date.fromisoformat(day)
    except (TypeError, ValueError):
        raise HTTPException(409, "Açık iş günü doğrulanamadı") from None
    if await db.night_audit_runs.find_one({"tenant_id": tenant_id, "business_date": day, "status": {"$in": ["completed", "completed_with_exceptions"]}}, session=session):
        raise HTTPException(409, "Kapalı iş gününe hizmet ücreti işlenemez")
    # A simultaneous day close changes the same document: conflict + retry,
    # not a write committed to a day that closed while we were posting.
    changed = await db.tenant_settings.update_one({"tenant_id": tenant_id, "business_date": day}, {"$inc": {"department_post_revision": 1}}, session=session)
    if changed.matched_count != 1:
        raise HTTPException(409, "İş günü değişti; hizmet aktarımı geri alındı")
    now = datetime.now(UTC).isoformat()
    charge = {
        "_id": f"department:{kind}:{tenant_id}:{sid}",
        "id": cid,
        "tenant_id": tenant_id,
        "booking_id": bid,
        "folio_id": folio["id"],
        source_field: sid,
        "charge_type": kind,
        "charge_category": kind,
        "description": source["description"],
        "amount": float(gross - (tax or 0)),
        "subtotal": float(gross - (tax or 0)),
        "quantity": 1,
        "total": float(gross),
        "currency": code,
        "business_date": day,
        "posted_at": now,
        "posted_by": actor_id,
        "service_date": source.get("service_date"),
        "service_time": source.get("service_time"),
        "source_fingerprint": fingerprint,
        "voided": False,
        "tax_breakdown": {"vat": float(tax)} if tax is not None else None,
        "vat_amount": float(tax) if tax is not None else None,
        "tax_amount": 0 if tax is not None else None,
        "is_complimentary": bool(full_comp),
        "complimentary_original_amount": float(original) if full_comp else None,
    }
    if kind in {"transfer", "parking"}:
        charge["line_no"] = 0
    if kind == "mice":
        charge.update(mice_event_id=sid, department="mice")
    await db.folio_charges.insert_one(dict(charge), session=session)
    if kind == "mice":
        legacy = await db.folio_postings.find_one({"tenant_id": tenant_id, "source": "mice_module", "reference": sid, "posting_type": "CHARGE"}, session=session)
        if legacy and (money(legacy.get("amount")) != original or legacy.get("currency") != code or legacy.get("reservation_id") != bid):
            raise HTTPException(409, "Eski MICE aktarım kaydı kaynakla uyuşmuyor")
        posting = {
            "tenant_id": tenant_id,
            "reservation_id": bid,
            "folio_id": folio["id"],
            "folio_charge_id": cid,
            "transaction_code": "MICE",
            "description": source["description"],
            "amount": float(gross),
            "currency": code,
            "posting_type": "CHARGE",
            "source": "mice_module",
            "reference": sid,
            "business_date": day,
        }
        if legacy:
            await db.folio_postings.update_one({"_id": legacy["_id"], "tenant_id": tenant_id}, {"$set": {**posting, "reconciled_at": now}}, session=session)
        else:
            await db.folio_postings.insert_one({"_id": f"mice-charge:{tenant_id}:{sid}", "id": cid, "posted_at": now, **posting}, session=session)
    snapshot = (await folio_snapshots(db, tenant_id, [folio], fallback_currency=code, session=session))[folio["id"]]
    balance = snapshot["balance_by_currency"].get(code, 0)
    await db.folios.update_one({"tenant_id": tenant_id, "id": folio["id"]}, {"$set": {"balance": balance}}, session=session)
    await refresh_booking_payment_state(db, tenant_id, bid, session=session, strict=True)
    entry = build_audit_entry(
        actor_id,
        tenant_id,
        "reservation",
        bid,
        kind + "_charge_posted",
        {
            "source_id": sid,
            "folio_id": folio["id"],
            "charge_id": cid,
            "total": float(gross),
            "currency": code,
            "business_date": day,
            "source_fingerprint": fingerprint,
            "reason": source.get("reason"),
            "legacy_embedded_charge_ids": [row.get("id") for row in folio.get("charges", []) if kind == "concierge" and row.get("concierge_request_id") == sid],
        },
    )
    await append_audit_log(db, entry, session=session, require_chain=True)
    charge.pop("_id")
    return {"charge": charge, "replayed": False}


async def complete_concierge(db, tenant_id, request_id, update, actor_id):
    async def transaction(session):
        current = await db.concierge_requests.find_one({"tenant_id": tenant_id, "_id": request_id}, session=session)
        if not current:
            raise HTTPException(404, "Talep bulunamadı")
        if current.get("folio_charge_id") and any(
            field in update and update[field] != current.get(field) for field in ("amount", "currency", "booking_id", "folio_id", "charge_to_folio", "type", "details", "date", "time", "notes")
        ):
            raise HTTPException(409, "Ücretlendirilmiş hizmet kaynağı değiştirilemez")
        merged = {**current, **update}
        source = {
            "kind": "concierge",
            "id": request_id,
            "booking_id": merged.get("booking_id"),
            "folio_id": merged.get("folio_id"),
            "currency": merged.get("currency"),
            "gross": merged.get("amount"),
            "tax": None,
            "description": "Concierge — " + str(merged.get("details") or merged.get("type") or "Hizmet"),
            "service_date": merged.get("date"),
            "service_time": merged.get("time"),
            "reason": merged.get("notes"),
        }
        posted = await post_source_charge(db, tenant_id, source, actor_id, session=session)
        update_fields = {**update, "folio_charge_id": posted["charge"]["id"]}
        if not posted["replayed"]:
            update_fields["charged_at"] = posted["charge"]["posted_at"]
        await db.concierge_requests.update_one({"tenant_id": tenant_id, "_id": request_id}, {"$set": update_fields}, session=session)
        result = await db.concierge_requests.find_one({"tenant_id": tenant_id, "_id": request_id}, session=session)
        result["id"] = str(result.pop("_id"))
        return result

    current = await db.concierge_requests.find_one({"tenant_id": tenant_id, "_id": request_id}) or {}
    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("concierge", request_id), ("booking", current.get("booking_id"))], callback=transaction
    )
    from core.report_cache import invalidate_financial_report_caches

    invalidate_financial_report_caches(tenant_id)
    return result


async def post_mice_event(db, tenant_id, event_id, actor_id, *, completion=None):
    async def transaction(session):
        if completion:
            before, update = completion
            result = await db.mice_events.update_one({"tenant_id": tenant_id, "id": event_id, "status": before["status"], "updated_at": before.get("updated_at")}, {"$set": update}, session=session)
            if result.matched_count != 1:
                raise HTTPException(409, "Etkinlik durumu değişti; sayfayı yenileyin")
        event = await db.mice_events.find_one({"tenant_id": tenant_id, "id": event_id}, session=session)
        if not event or event.get("status") != "completed":
            raise HTTPException(409, "Folyoya aktarım için tamamlanmış aynı tesis etkinliği gerekli")
        totals = event.get("totals") or {}
        spaces = event.get("space_bookings") or []
        starts = str(spaces[0].get("starts_at") or "") if spaces else ""
        source = {
            "kind": "mice",
            "id": event_id,
            "booking_id": event.get("reservation_id"),
            "folio_id": event.get("folio_id"),
            "currency": event.get("currency"),
            "gross": totals.get("grand_total"),
            "tax": totals.get("tax_total"),
            "description": "Etkinlik: " + str(event.get("name") or "MICE"),
            "service_date": event.get("start_date"),
            "service_time": starts[11:16] or None,
            "reason": event.get("notes"),
        }
        posted = await post_source_charge(db, tenant_id, source, actor_id, session=session)
        await db.mice_events.update_one({"tenant_id": tenant_id, "id": event_id}, {"$set": {"folio_charge_id": posted["charge"]["id"], "folio_id": posted["charge"]["folio_id"]}}, session=session)
        return posted

    event = await db.mice_events.find_one({"tenant_id": tenant_id, "id": event_id}) or {}
    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("mice", event_id), ("booking", event.get("reservation_id"))], callback=transaction
    )
    from core.report_cache import invalidate_financial_report_caches

    invalidate_financial_report_caches(tenant_id)
    return result


async def post_transport_charge(db, tenant_id, booking_doc, actor_id):
    """Keep the service timestamp separate from the current open ledger day."""
    schedule = booking_doc.get("schedule") or {}
    pickup = str(schedule.get("pickup_at") or "")
    source = {
        "kind": "transfer" if booking_doc.get("kind") == "transfer_vehicle" else "parking",
        "id": booking_doc["id"],
        "booking_id": booking_doc.get("booking_id"),
        "folio_id": booking_doc.get("folio_id"),
        "currency": booking_doc["currency"],
        "gross": booking_doc["total"],
        "tax": None,
        "description": ("Transfer — " if pickup else "Otopark — ") + str(booking_doc.get("resource_name") or "Hizmet"),
        "service_date": pickup[:10] or schedule.get("start_date"),
        "service_time": pickup[11:16] or None,
        "reason": booking_doc.get("note"),
    }

    async def transaction(session):
        return await post_source_charge(db, tenant_id, source, actor_id, session=session)

    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("transport", booking_doc["id"]), ("booking", source["booking_id"])], callback=transaction
    )
    from core.report_cache import invalidate_financial_report_caches

    invalidate_financial_report_caches(tenant_id)
    return result
