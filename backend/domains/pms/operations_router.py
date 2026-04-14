import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Body, HTTPException

from core.security import get_current_user
from db import get_db
from models.schemas import User

router = APIRouter(prefix="/api", tags=["PMS / Operations"])


def _safe_int(val, default=0):
    try:
        return int(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid integer value: {val}")


def _safe_float(val, default=0.0):
    try:
        return float(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid numeric value: {val}")


@router.get("/concierge/requests")
async def get_concierge_requests(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.concierge_requests.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("created_at", -1).to_list(500)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"requests": docs}


@router.post("/concierge/requests")
async def create_concierge_request(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "type": body.get("type", "other"),
        "room_number": body.get("room_number", ""),
        "guest_name": body.get("guest_name", ""),
        "details": body.get("details", ""),
        "date": body.get("date", now.strftime("%Y-%m-%d")),
        "time": body.get("time", ""),
        "pax": _safe_int(body.get("pax", 1), 1),
        "notes": body.get("notes", ""),
        "priority": body.get("priority", "normal"),
        "status": "pending",
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.concierge_requests.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.patch("/concierge/requests/{request_id}")
async def update_concierge_request(request_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    new_status = body.get("status", "updated")
    result = await db.concierge_requests.update_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat(), "updated_by": current_user.email}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"id": request_id, "status": new_status}


@router.get("/banquet/events")
async def get_banquet_events(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.banquet_events.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("date", -1).to_list(500)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"events": docs}


@router.post("/banquet/events")
async def create_banquet_event(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "event_name": body.get("event_name", ""),
        "company": body.get("company", ""),
        "contact_name": body.get("contact_name", ""),
        "contact_phone": body.get("contact_phone", ""),
        "contact_email": body.get("contact_email", ""),
        "room_name": body.get("room_name", ""),
        "date": body.get("date", ""),
        "start_time": body.get("start_time", ""),
        "end_time": body.get("end_time", ""),
        "setup_type": body.get("setup_type", ""),
        "attendees": _safe_int(body.get("attendees", 0)),
        "guaranteed_pax": _safe_int(body.get("guaranteed_pax", 0)),
        "menu_type": body.get("menu_type", ""),
        "menu_details": body.get("menu_details", ""),
        "av_equipment": body.get("av_equipment", []),
        "special_requests": body.get("special_requests", ""),
        "decorations": body.get("decorations", ""),
        "price_per_person": _safe_float(body.get("price_per_person", 0)),
        "total_price": _safe_float(body.get("total_price", 0)),
        "deposit_amount": _safe_float(body.get("deposit_amount", 0)),
        "status": body.get("status", "tentative"),
        "billing_instructions": body.get("billing_instructions", ""),
        "notes": body.get("notes", ""),
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.banquet_events.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.patch("/banquet/events/{event_id}")
async def update_banquet_event(event_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    update_fields = {k: v for k, v in body.items() if k not in ("id", "_id", "tenant_id")}
    update_fields["updated_at"] = datetime.utcnow().isoformat()
    result = await db.banquet_events.update_one(
        {"_id": event_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"id": event_id, "status": "updated"}


@router.post("/kbs/send")
async def send_kbs_notification(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    booking_id = body.get("booking_id")
    kbs_ref = str(uuid.uuid4())[:8].upper()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "booking_id": booking_id,
        "kbs_reference": kbs_ref,
        "status": "sent",
        "sent_at": now.isoformat(),
        "sent_by": current_user.email,
        "guest_data": body.get("guest_data", {}),
    }
    await db.kbs_notifications.insert_one(doc)
    if booking_id:
        await db.bookings.update_one(
            {"_id": booking_id, "tenant_id": current_user.tenant_id},
            {"$set": {"kbs_status": "sent", "kbs_sent_at": now.isoformat(), "kbs_reference": kbs_ref}}
        )
    return {"status": "sent", "kbs_reference": kbs_ref, "sent_at": now.isoformat()}


@router.post("/kbs/send-batch")
async def send_kbs_batch(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    booking_ids = body.get("booking_ids", [])
    results = []
    for bid in booking_ids:
        kbs_ref = str(uuid.uuid4())[:8].upper()
        doc = {
            "_id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "booking_id": bid,
            "kbs_reference": kbs_ref,
            "status": "sent",
            "sent_at": now.isoformat(),
            "sent_by": current_user.email,
        }
        try:
            await db.kbs_notifications.insert_one(doc)
            await db.bookings.update_one(
                {"_id": bid, "tenant_id": current_user.tenant_id},
                {"$set": {"kbs_status": "sent", "kbs_sent_at": now.isoformat(), "kbs_reference": kbs_ref}}
            )
        except Exception:
            results.append({"booking_id": bid, "status": "error"})
            continue
        results.append({"booking_id": bid, "kbs_reference": kbs_ref})
    return {"status": "sent", "count": len(results), "results": results, "sent_at": now.isoformat()}


@router.get("/kbs/history")
async def get_kbs_history(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.kbs_notifications.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("sent_at", -1).to_list(500)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"notifications": docs}


@router.get("/kvkk/requests")
async def get_kvkk_requests(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.kvkk_requests.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("created_at", -1).to_list(500)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"requests": docs}


@router.post("/kvkk/requests")
async def create_kvkk_request(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_name": body.get("guest_name", ""),
        "type": body.get("type", "access"),
        "details": body.get("details", ""),
        "status": "pending",
        "date": now.strftime("%Y-%m-%d"),
        "response_date": None,
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.kvkk_requests.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.patch("/kvkk/requests/{request_id}")
async def update_kvkk_request(request_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    update_fields = {k: v for k, v in body.items() if k not in ("id", "_id", "tenant_id")}
    update_fields["updated_at"] = datetime.utcnow().isoformat()
    if body.get("status") == "completed":
        update_fields["response_date"] = datetime.utcnow().strftime("%Y-%m-%d")
    result = await db.kvkk_requests.update_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"id": request_id, "status": update_fields.get("status", "updated")}


@router.get("/kvkk/consents")
async def get_kvkk_consents(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.kvkk_consents.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("date", -1).to_list(500)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"consents": docs}


@router.get("/kvkk/audit-log")
async def get_kvkk_audit_log(current_user: User = Depends(get_current_user)):
    db = get_db()
    docs = await db.kvkk_audit_log.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("timestamp", -1).to_list(200)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"logs": docs}


@router.patch("/pms/guests/{guest_id}/preferences")
async def update_guest_preferences(guest_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    update_fields = {}
    if "preferences" in body:
        update_fields["preferences"] = body["preferences"]
    if "preference_notes" in body:
        update_fields["preference_notes"] = body["preference_notes"]
    if "birthday" in body:
        update_fields["birthday"] = body["birthday"]
    if "anniversary" in body:
        update_fields["anniversary"] = body["anniversary"]
    if "vip_level" in body:
        update_fields["vip_level"] = body["vip_level"]
    if "id_number" in body:
        update_fields["id_number"] = body["id_number"]
    if "birth_date" in body:
        update_fields["birth_date"] = body["birth_date"]
    update_fields["preferences_updated_at"] = datetime.utcnow().isoformat()

    result = await db.guests.update_one(
        {"_id": guest_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Guest not found")

    await db.kvkk_audit_log.insert_one({
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "action": "Misafir tercihleri guncellendi",
        "user": current_user.email,
        "target": guest_id,
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {"id": guest_id, "status": "updated"}


@router.post("/frontdesk/booking/{booking_id}/routing-rules")
async def save_routing_rules(booking_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    rules = body.get("rules", [])
    result = await db.bookings.update_one(
        {"_id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": {"routing_rules": rules, "routing_updated_at": datetime.utcnow().isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"booking_id": booking_id, "rules_count": len(rules), "status": "saved"}


@router.patch("/pms/rooms/{room_id}/features")
async def update_room_features(room_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    update_fields = {k: v for k, v in body.items() if k not in ("id", "_id", "tenant_id")}
    update_fields["features_updated_at"] = datetime.utcnow().isoformat()
    result = await db.rooms.update_one(
        {"_id": room_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"id": room_id, "status": "updated"}


@router.get("/revenue/settings")
async def get_revenue_settings(current_user: User = Depends(get_current_user)):
    db = get_db()
    doc = await db.revenue_settings.find_one({"tenant_id": current_user.tenant_id})
    if not doc:
        return {"hurdle_rates": {}, "day_pricing": {}, "overbooking": {"enabled": False, "max_percentage": 5, "walk_compensation": "upgrade_nearby", "walk_amount": 0}}
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.put("/revenue/settings")
async def save_revenue_settings(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    await db.revenue_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {
            "tenant_id": current_user.tenant_id,
            "hurdle_rates": body.get("hurdle_rates", {}),
            "day_pricing": body.get("day_pricing", {}),
            "overbooking": body.get("overbooking", {}),
            "updated_at": now.isoformat(),
            "updated_by": current_user.email,
        }},
        upsert=True
    )
    return {"status": "saved", "updated_at": now.isoformat()}


@router.post("/revenue/walk-out")
async def process_walk_out(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_name": body.get("guest_name", ""),
        "room_type": body.get("room_type", ""),
        "compensation_type": body.get("compensation_type", ""),
        "compensation_amount": _safe_float(body.get("compensation_amount", 0)),
        "nearby_hotel": body.get("nearby_hotel", ""),
        "notes": body.get("notes", ""),
        "processed_at": now.isoformat(),
        "processed_by": current_user.email,
    }
    await db.walk_out_records.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc
