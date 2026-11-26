"""Serialize POS source writers with the immutable daily source snapshot."""
from datetime import UTC, date, datetime

from fastapi import HTTPException


async def prepare_day_lock(database):
    await database.pos_closure_locks.create_index(
        [("tenant_id", 1), ("kind", 1), ("resource_id", 1)],
        unique=True, name="ux_pos_daily_closure_lock",
    )


async def touch_day_lock(database, tenant_id, day, session):
    try:
        day = date.fromisoformat(str(day)[:10]).isoformat()
    except ValueError as exc:
        raise HTTPException(409, "POS işlem iş günü doğrulanamadı.") from exc
    now = datetime.now(UTC).isoformat()
    await database.pos_closure_locks.update_one(
        {"tenant_id": tenant_id, "kind": "pos_daily_closure", "resource_id": day},
        {"$inc": {"write_epoch": 1}, "$set": {"touched_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True, session=session,
    )
    return day


async def assert_day_writable(database, tenant_id, day, session):
    day = await touch_day_lock(database, tenant_id, day, session)
    if await database.pos_closures.find_one({"tenant_id": tenant_id, "closure_date": day}, {"_id": 1}, session=session):
        raise HTTPException(409, "Bu iş gününün POS kapanışı tamamlandı; yeni adisyon, tahsilat veya iade kaydedilemez.")


async def posting_day(database, tenant_id):
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"business_date": 1})
    try:
        return date.fromisoformat(str((settings or {}).get("business_date") or "")[:10]).isoformat()
    except ValueError as exc:
        raise HTTPException(409, "POS işleminden önce otel iş günü doğrulanmalıdır.") from exc


async def persist_direct_transaction(database, tenant_id, transaction):
    from core.booking_atomicity import with_resource_locks

    day = await posting_day(database, tenant_id)
    settings = await database.hotel_settings.find_one({"tenant_id": tenant_id}, {"currency": 1})
    currency = str((settings or {}).get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(409, "POS işlem para birimi doğrulanamadı.")
    document = {**transaction, "transaction_date": day, "business_date": day, "currency": currency}
    await prepare_day_lock(database)

    async def commit(session):
        await assert_day_writable(database, tenant_id, day, session)
        await database.pos_transactions.insert_one(dict(document), session=session)

    await with_resource_locks(client=database.client, db=database, tenant_id=tenant_id,
                             locks_collection="pos_closure_locks", resources=[], callback=commit)
    return document
