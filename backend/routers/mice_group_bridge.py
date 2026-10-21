"""Canonical group-master charge handoff; no synthetic room reservation."""
from datetime import UTC, datetime

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks
from core.business_date_service import ensure_business_date_initialized
from core.mice_integrity import money, rounded


async def post_group_event(db, tid, event, *, session=None):
    total = money((event.get("totals") or {}).get("grand_total"))
    if not total:
        return
    day = (await ensure_business_date_initialized(db, tid))["business_date"]
    async def post(session):
        key = f"mice-group-charge:{tid}:{event['id']}"
        if await db.folio_charges.find_one({"_id": key, "tenant_id": tid}, session=session):
            return
        group = await db.group_blocks.find_one({"tenant_id": tid, "id": event["group_block_id"], "status": {"$nin": ["cancelled", "released"]}}, session=session)
        folio = await db.folios.find_one({"tenant_id": tid, "id": (group or {}).get("master_folio_id"), "status": "open", "currency": event["currency"]}, session=session)
        if not folio:
            raise HTTPException(409, "Grup ana folyosu kapalı, eksik veya para birimi farklı")
        tax = money((event.get("totals") or {}).get("tax_total"))
        await db.folio_charges.insert_one({"_id": key, "id": key, "tenant_id": tid, "folio_id": folio["id"], "group_block_id": group["id"],
                                           "mice_event_id": event["id"], "description": f"Banket: {event['name']}", "charge_category": "banquet", "department": "mice",
                                           "quantity": 1, "unit_price": rounded(total - tax), "amount": rounded(total - tax), "tax_amount": float(tax), "total": float(total),
                                           "currency": event["currency"], "voided": False, "business_date": day, "date": datetime.now(UTC).isoformat(), "external_reference": key}, session=session)
        await db.folios.update_one({"tenant_id": tid, "id": folio["id"]}, {"$inc": {"balance": float(total), "total_charges": float(total)}}, session=session)
    if session is not None:
        await post(session)
    else:
        await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("group_folio", event["group_block_id"])], callback=post)
