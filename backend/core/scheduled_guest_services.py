"""Activity / function-space capacity, immutable quotes and native folio handoff."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, Field

from core.audit_chain import append_audit_log
from core.booking_atomicity import with_resource_locks
from core.department_folio import money, post_source_charge
from core.guest_service_folio import _fingerprint, inclusive_tax
from core.mice_integrity import local_instant
from core.report_cache import invalidate_financial_report_caches
from shared_kernel.audit_helper import build_audit_entry


class ScheduledFolioInput(BaseModel):
    reservation_id: str
    folio_id: str
    quote_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    billing_basis: str = "per_booking"
    reason: str = Field(min_length=3, max_length=1000)


async def timezone_for(db, tenant_id, session=None):
    settings = await db.hotel_settings.find_one({"tenant_id": tenant_id}, session=session) or {}
    try:
        return ZoneInfo(settings.get("timezone") or "Europe/Istanbul")
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(409, "Tesis saat dilimi doğrulanamadı") from None


def window(row, zone):
    try:
        start = local_instant(row["starts_at"], str(zone)).astimezone(UTC)
        end = local_instant(row["ends_at"], str(zone)).astimezone(UTC)
        if end <= start:
            raise ValueError
        return start, end
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, "Takvimde geçersiz/belirsiz saat var; kaynak incelemesi gerekli") from None


async def day_bookings(db, kind, tenant_id, day=None, resource_id=None, session=None):
    collection, field = (db.activity_bookings, "resource_id") if kind == "activity" else (db.function_bookings, "room_id")
    query = {"tenant_id": tenant_id, **({field: resource_id} if resource_id else {})}
    rows = await collection.find(query, {"_id": 0}, session=session).to_list(5001)
    if len(rows) > 5000:
        raise HTTPException(503, "Takvim sorgu sınırına ulaştı; kaynak filtresi kullanın")
    zone = await timezone_for(db, tenant_id, session)
    if day:
        try:
            start = datetime.combine(date.fromisoformat(day), datetime.min.time(), zone).astimezone(UTC)
        except ValueError:
            raise HTTPException(422, "Tarih YYYY-MM-DD olmalı") from None
        end = (start.astimezone(zone) + timedelta(days=1)).astimezone(UTC)
        rows = [row for row in rows if window(row, zone)[0] < end and window(row, zone)[1] > start]
    for row in rows:
        start, end = window(row, zone)
        row["starts_at"], row["ends_at"] = start.astimezone(zone).isoformat(), end.astimezone(zone).isoformat()
    return sorted(rows, key=lambda row: window(row, zone)[0])


async def _audit(db, user, kind, record_id, action, details, session):
    await append_audit_log(db, build_audit_entry(user.id, user.tenant_id, kind, record_id, action, details), session=session, require_chain=True)


async def create_scheduled_booking(db, kind, payload, user):
    collection = db.activity_bookings if kind == "activity" else db.function_bookings
    rid = payload.get("resource_id") if kind == "activity" else payload.get("room_id")
    token = payload.get("request_id")
    record_id = str(uuid5(NAMESPACE_URL, f"syroce:{kind}:{user.tenant_id}:{token}")) if token else str(uuid4())
    request_hash = _fingerprint(payload)
    await collection.create_index([("tenant_id", 1), ("id", 1)], unique=True)

    async def transaction(session):
        prior = await collection.find_one({"tenant_id": user.tenant_id, "id": record_id}, session=session)
        if prior:
            if prior.get("request_hash") != request_hash:
                raise HTTPException(409, "Aynı takvim anahtarı farklı içerikle kullanılamaz")
            prior.pop("_id", None)
            return prior
        zone = await timezone_for(db, user.tenant_id, session)
        data = dict(payload)
        if kind == "activity":
            catalogue = await db.activities.find_one({"tenant_id": user.tenant_id, "id": payload["activity_id"], "active": True}, session=session)
            resource = await db.activity_resources.find_one({"tenant_id": user.tenant_id, "id": rid, "active": True}, session=session)
            guest = await db.guests.find_one({"tenant_id": user.tenant_id, "id": payload["guest_id"]}, session=session)
            if not catalogue or not resource or not guest:
                raise HTTPException(404, "Aynı tesiste aktif aktivite/kaynak/misafir bulunamadı")
            if resource.get("activity_types") and catalogue.get("type") not in resource["activity_types"]:
                raise HTTPException(400, "Kaynak bu aktivite tipini desteklemiyor")
            duration = payload.get("duration_min") or catalogue["duration_min"]
            data["duration_min"] = duration
            data["ends_at"] = (local_instant(payload["starts_at"], str(zone)) + timedelta(minutes=duration)).isoformat()
            capacity = min(resource.get("capacity", 1), catalogue.get("capacity", 1))
        else:
            catalogue = await db.function_rooms.find_one({"tenant_id": user.tenant_id, "id": rid, "active": True}, session=session)
            if not catalogue:
                raise HTTPException(404, "Aynı tesiste aktif salon bulunamadı")
            if payload["attendees"] > catalogue["capacity"] or (catalogue.get("supported_setups") and payload["setup_type"] not in catalogue["supported_setups"]):
                raise HTTPException(400, "Kapasite veya kurulum salon tanımına uygun değil")
            capacity = 1
        start, end = window(data, zone)
        prior_rows = await day_bookings(db, kind, user.tenant_id, resource_id=rid, session=session)
        events = [(start, 1), (end, -1)]
        for row in prior_rows:
            if row.get("status") == "cancelled":
                continue
            left, right = window(row, zone)
            if left < end and right > start:
                events.extend([(max(left, start), 1), (min(right, end), -1)])
        used = 0
        for _, delta in sorted(events):
            used += delta
            if used > capacity:
                raise HTTPException(409, "Kaynak seçilen zaman aralığında dolu")
        data.update(
            _id=f"scheduled:{kind}:{user.tenant_id}:{record_id}",
            id=record_id,
            tenant_id=user.tenant_id,
            status="booked",
            created_by=user.email,
            created_at=datetime.now(UTC).isoformat(),
            request_hash=request_hash,
        )
        await collection.insert_one(dict(data), session=session)
        await _audit(db, user, kind, record_id, f"{kind}_booking_created", {"resource_id": rid, "starts_at": data["starts_at"], "ends_at": data["ends_at"], "reason": data.get("note")}, session)
        data.pop("_id")
        return data

    return await with_resource_locks(client=db.client, db=db, tenant_id=user.tenant_id, locks_collection="folio_locks", resources=[(f"{kind}_resource", rid), (kind, record_id)], callback=transaction)


async def cancel_scheduled_booking(db, kind, record_id, user):
    collection = db.activity_bookings if kind == "activity" else db.function_bookings

    async def transaction(session):
        row = await collection.find_one({"tenant_id": user.tenant_id, "id": record_id}, session=session)
        if not row:
            raise HTTPException(404, "Takvim kaydı bulunamadı")
        if row.get("folio_charge_id") or row.get("status") == "completed":
            raise HTTPException(409, "Tamamlanmış/ücretlendirilmiş hizmet iptal edilemez; yetkili folyo iptal/iade akışı gerekli")
        if row.get("status") != "cancelled":
            await collection.update_one({"_id": row["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": datetime.now(UTC).isoformat(), "cancelled_by": user.id}}, session=session)
            await _audit(db, user, kind, record_id, f"{kind}_booking_cancelled", {"reason": "Operatör takvim iptali"}, session)
        return {"ok": True}

    return await with_resource_locks(client=db.client, db=db, tenant_id=user.tenant_id, locks_collection="folio_locks", resources=[(kind, record_id)], callback=transaction)


async def scheduled_quote(db, kind, tenant_id, record_id, basis, session=None):
    collection = db.activity_bookings if kind == "activity" else db.function_bookings
    row = await collection.find_one({"tenant_id": tenant_id, "id": record_id}, session=session)
    if not row or row.get("status") not in {"booked", "completed"}:
        raise HTTPException(409, "Ücretlendirilebilir takvim kaydı bulunamadı")
    if row.get("status") == "completed" and not (row.get("folio_source_snapshot") and row.get("folio_charge_id")):
        raise HTTPException(409, "Eski tamamlanmış hizmetin ücret kaynağı incelemesi gerekli")
    if row.get("folio_source_snapshot"):
        return row["folio_source_snapshot"]
    zone = await timezone_for(db, tenant_id, session)
    start, end = window(row, zone)
    if kind == "activity":
        catalogue = await db.activities.find_one({"tenant_id": tenant_id, "id": row["activity_id"], "active": True}, session=session)
        if basis != "per_booking":
            raise HTTPException(422, "Aktivite fiyatı katılım başınadır")
        units = Decimal(1)
        rate_field = "price"
    else:
        catalogue = await db.function_rooms.find_one({"tenant_id": tenant_id, "id": row["room_id"], "active": True}, session=session)
        if basis not in {"hourly", "daily"}:
            raise HTTPException(422, "Saatlik veya günlük tarife açıkça seçilmeli")
        units = Decimal(str((end - start).total_seconds())) / (Decimal(3600) if basis == "hourly" else Decimal(86400))
        rate_field = "hourly_rate" if basis == "hourly" else "daily_rate"
    if not catalogue or not catalogue.get("currency"):
        raise HTTPException(409, "Kaynak hizmetin fiyat/para birimi doğrulanamadı")
    gross = (money(catalogue.get(rate_field)) * units).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    tax = inclusive_tax(gross, catalogue.get("tax_rate"))
    snapshot = {
        "kind": kind,
        "id": record_id,
        "currency": catalogue["currency"],
        "gross": str(gross),
        "tax": str(tax) if tax is not None else None,
        "category": kind,
        "description": ("Aktivite — " if kind == "activity" else "Salon — ") + str(catalogue.get("name")),
        "service_date": start.astimezone(zone).date().isoformat(),
        "service_time": start.astimezone(zone).strftime("%H:%M"),
        "billing_basis": basis,
        "billing_units": str(units),
        "unit_price": str(money(catalogue.get(rate_field))),
        "starts_at": row["starts_at"],
        "ends_at": row["ends_at"],
    }
    snapshot["quote_hash"] = _fingerprint(snapshot)
    return snapshot


async def post_scheduled_folio(db, kind, record_id, payload, user):
    collection = db.activity_bookings if kind == "activity" else db.function_bookings
    request_hash = _fingerprint(payload.model_dump())

    async def transaction(session):
        row = await collection.find_one({"tenant_id": user.tenant_id, "id": record_id}, session=session)
        if not row:
            raise HTTPException(404, "Takvim kaydı bulunamadı")
        if row.get("folio_request_hash") and row["folio_request_hash"] != request_hash:
            raise HTTPException(409, "Ücretlendirilmiş hizmetin hedefi/kapsamı değiştirilemez")
        snapshot = await scheduled_quote(db, kind, user.tenant_id, record_id, payload.billing_basis, session)
        if snapshot["quote_hash"] != payload.quote_hash:
            raise HTTPException(409, "Hizmet tarifesi/takvimi değişti; önizlemeyi yenileyin")
        target = await db.bookings.find_one({"tenant_id": user.tenant_id, "id": payload.reservation_id}, session=session)
        if not target or (kind == "activity" and target.get("guest_id") != row.get("guest_id")):
            raise HTTPException(409, "Aktivite misafiri ile seçilen konaklama uyuşmuyor")
        source = {**snapshot, "booking_id": payload.reservation_id, "folio_id": payload.folio_id, "reason": payload.reason}
        posted = await post_source_charge(db, user.tenant_id, source, user.id, session=session)
        if not posted["replayed"]:
            await collection.update_one(
                {"_id": row["_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "folio_source_snapshot": snapshot,
                        "folio_request_hash": request_hash,
                        "folio_id": posted["charge"]["folio_id"],
                        "reservation_id": payload.reservation_id,
                        "folio_charge_id": posted["charge"]["id"],
                        "completed_at": datetime.now(UTC).isoformat(),
                        "completed_by": user.id,
                    }
                },
                session=session,
            )
        return {"success": True, "charge": posted["charge"], "replayed": posted["replayed"]}

    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=user.tenant_id, locks_collection="folio_locks", resources=[(kind, record_id), ("booking", payload.reservation_id)], callback=transaction
    )
    invalidate_financial_report_caches(user.tenant_id)
    return result
