"""Shared tenant/table validation and atomic restaurant reservation identity."""

import uuid
from datetime import UTC, date, datetime, time

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.pms.pos_extensions._idem import ensure_compound_unique


async def create(db, tenant_id, actor_id, *, outlet_id, table_id, guest_name, pax, res_date, res_time, notes=None):
    try:
        day = date.fromisoformat(res_date).isoformat()
        hour = time.fromisoformat(res_time).strftime("%H:%M")
        if not guest_name.strip() or not 1 <= pax <= 1000:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Geçerli isim, tarih, saat ve kişi sayısı girin.") from None
    table = await db.table_layouts.find_one({"tenant_id": tenant_id, "outlet_id": outlet_id, "id": table_id})
    outlet = await db.pos_outlets.find_one({"tenant_id": tenant_id, "id": outlet_id, "status": {"$ne": "deleted"}})
    if not table or not outlet:
        raise HTTPException(404, "Bu satış noktasına ait masa bulunamadı.")
    await ensure_compound_unique(
        db.pos_table_reservations,
        [("tenant_id", 1), ("outlet_id", 1), ("table_id", 1), ("res_date", 1), ("res_time", 1)],
        partial_filter={"status": {"$in": ["confirmed", "seated"]}},
        name="pos_table_active_slot",
    )
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "outlet_id": outlet_id,
        "table_id": table_id,
        "table_number": str(table["table_number"]),
        "guest_name": guest_name.strip(),
        "pax": pax,
        "res_date": day,
        "res_time": hour,
        "notes": notes,
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": actor_id,
    }
    try:
        await db.pos_table_reservations.insert_one(dict(row))
    except DuplicateKeyError:
        raise HTTPException(409, "Masa bu saatte zaten rezerve.") from None
    return row
