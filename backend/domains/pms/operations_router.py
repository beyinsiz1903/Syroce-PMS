import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v100  # v100 DW
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW
from modules.pms_core.role_permission_service import require_op  # v97 DW

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
async def get_concierge_requests(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    docs = await db.concierge_requests.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    total = await db.concierge_requests.count_documents(query)
    return {"requests": docs, "total": total}


@router.post("/concierge/requests")
async def create_concierge_request(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
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
async def update_concierge_request(request_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    new_status = body.get("status", "updated")
    result = await db.concierge_requests.update_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat(), "updated_by": current_user.email}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"id": request_id, "status": new_status}


@router.get("/banquet/events")
async def get_banquet_events(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    docs = await db.banquet_events.find(query).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    total = await db.banquet_events.count_documents(query)
    return {"events": docs, "total": total}


@router.post("/banquet/events")
async def create_banquet_event(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
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
async def update_banquet_event(event_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
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
async def send_kbs_notification(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
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
async def send_kbs_batch(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
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
            import logging
            logging.getLogger(__name__).exception("KBS batch send failed for booking %s", bid)
            results.append({"booking_id": bid, "status": "error"})
            continue
        results.append({"booking_id": bid, "kbs_reference": kbs_ref})
    return {"status": "sent", "count": len(results), "results": results, "sent_at": now.isoformat()}


@router.get("/kbs/history")
async def get_kbs_history(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    docs = await db.kbs_notifications.find(query).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    total = await db.kbs_notifications.count_documents(query)
    return {"notifications": docs, "total": total}


@router.get("/kvkk/requests")
async def get_kvkk_requests(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    docs = await db.kvkk_requests.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    total = await db.kvkk_requests.count_documents(query)
    return {"requests": docs, "total": total}


@router.post("/kvkk/requests")
async def create_kvkk_request(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
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
async def update_kvkk_request(request_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
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
async def get_kvkk_consents(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    docs = await db.kvkk_consents.find(query).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    total = await db.kvkk_consents.count_documents(query)
    return {"consents": docs, "total": total}


@router.get("/kvkk/audit-log")
async def get_kvkk_audit_log(skip: int = 0, limit: int = 200, current_user: User = Depends(get_current_user)):
    docs = await db.kvkk_audit_log.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"logs": docs}


@router.patch("/pms/guests/{guest_id}/preferences")
async def update_guest_preferences(guest_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
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


@router.get("/frontdesk/booking/{booking_id}/routing-rules")
async def get_routing_rules(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Bir rezervasyona tanımlı masraf yönlendirme kurallarını döner.
    Boş dönerse henüz tanım yok demektir; UI default akışı misafir folyosuna yansıtır.
    """
    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"_id": 0, "routing_rules": 1, "routing_updated_at": 1},
    )
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {
        "booking_id": booking_id,
        "rules": booking.get("routing_rules") or [],
        "updated_at": booking.get("routing_updated_at"),
    }


@router.post("/frontdesk/booking/{booking_id}/routing-rules")
async def save_routing_rules(booking_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    rules = body.get("rules", [])
    for rule in rules:
        if rule.get("split_type") == "percentage":
            total_pct = sum(s.get("percentage", 0) for s in rule.get("splits", []))
            if abs(total_pct - 100) > 0.01:
                raise HTTPException(status_code=400, detail=f"Routing percentages must sum to 100%, got {total_pct}%")
    # Bug fix: bookings koleksiyonunda primary key `id` (UUID), `_id` değil.
    # Eski sürüm `_id` arıyordu → her çağrı 404 dönüyordu.
    result = await db.bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": {"routing_rules": rules, "routing_updated_at": datetime.utcnow().isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"booking_id": booking_id, "rules_count": len(rules), "status": "saved"}


@router.patch("/pms/rooms/{room_id}/features")
async def update_room_features(room_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
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
    doc = await db.revenue_settings.find_one({"tenant_id": current_user.tenant_id})
    if not doc:
        return {"hurdle_rates": {}, "day_pricing": {}, "overbooking": {"enabled": False, "max_percentage": 5, "walk_compensation": "upgrade_nearby", "walk_amount": 0}}
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.put("/revenue/settings")
async def save_revenue_settings(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
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
async def process_walk_out(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
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


@router.delete("/concierge/requests/{request_id}")
async def delete_concierge_request(request_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    result = await db.concierge_requests.delete_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Talep bulunamadi")
    return {"id": request_id, "status": "deleted"}


@router.delete("/banquet/events/{event_id}")
async def delete_banquet_event(event_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    result = await db.banquet_events.delete_one(
        {"_id": event_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Etkinlik bulunamadi")
    return {"id": event_id, "status": "deleted"}


@router.delete("/kvkk/requests/{request_id}")
async def delete_kvkk_request(request_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    result = await db.kvkk_requests.delete_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="KVKK talebi bulunamadi")
    return {"id": request_id, "status": "deleted"}


@router.post("/pms/bookings/{booking_id}/complimentary-approval")
async def request_complimentary_approval(booking_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v97 DW
):
    booking = await db.bookings.find_one({"_id": booking_id, "tenant_id": current_user.tenant_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    now = datetime.utcnow()
    approval_doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "booking_id": booking_id,
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "reason": body.get("reason", ""),
        "requested_by": current_user.email,
        "status": "pending_approval",
        "created_at": now.isoformat(),
    }
    await db.complimentary_approvals.insert_one(approval_doc)
    await db.bookings.update_one(
        {"_id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": {"complimentary_status": "pending_approval", "complimentary_reason": body.get("reason", "")}}
    )
    approval_doc["id"] = approval_doc.pop("_id")
    return approval_doc


@router.patch("/pms/bookings/{booking_id}/complimentary-approval/{approval_id}")
async def handle_complimentary_approval(booking_id: str, approval_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v97 DW
):
    action = body.get("action", "approve")
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
    approval = await db.complimentary_approvals.find_one(
        {"_id": approval_id, "booking_id": booking_id, "tenant_id": current_user.tenant_id}
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found for this booking")
    now = datetime.utcnow()
    new_status = "approved" if action == "approve" else "rejected"
    await db.complimentary_approvals.update_one(
        {"_id": approval_id},
        {"$set": {"status": new_status, "decided_by": current_user.email, "decided_at": now.isoformat()}}
    )
    booking_update = {"complimentary_status": new_status}
    if action == "approve":
        booking_update["rate_type"] = "complimentary"
    await db.bookings.update_one(
        {"_id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": booking_update}
    )
    return {"booking_id": booking_id, "approval_id": approval_id, "status": new_status}


@router.get("/pms/dayuse-bookings")
async def get_dayuse_bookings(current_user: User = Depends(get_current_user)):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    docs = await db.bookings.find({
        "tenant_id": current_user.tenant_id,
        "booking_type": "day_use",
        "status": "checked_in",
        "check_out": {"$regex": f"^{today}"}
    }).to_list(100)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"bookings": docs}


@router.post("/pms/dayuse-auto-checkout")
async def dayuse_auto_checkout(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    result = await db.bookings.update_many(
        {
            "tenant_id": current_user.tenant_id,
            "booking_type": "day_use",
            "status": "checked_in",
            "check_out": {"$lte": now.isoformat()}
        },
        {"$set": {"status": "checked_out", "actual_check_out": now.isoformat(), "auto_checkout": True}}
    )
    return {"checked_out_count": result.modified_count, "date": today}


@router.get("/pms/loyalty/tiers")
async def get_loyalty_tiers(current_user: User = Depends(get_current_user)):
    tiers = await db.loyalty_tiers.find({"tenant_id": current_user.tenant_id}).sort("min_points", 1).to_list(20)
    if not tiers:
        defaults = [
            {"name": "Silver", "min_points": 0, "max_points": 999, "benefits": ["Gec cikis (14:00)", "Hosgeldin icecegi"], "upgrade_eligible": False},
            {"name": "Gold", "min_points": 1000, "max_points": 4999, "benefits": ["Gec cikis (16:00)", "Oda yukseltme (musait)", "Ucretsiz minibar"], "upgrade_eligible": True},
            {"name": "Platinum", "min_points": 5000, "max_points": 19999, "benefits": ["Gec cikis (18:00)", "Garantili yukseltme", "Spa indirimi %20", "Club lounge erisimi"], "upgrade_eligible": True},
            {"name": "Diamond", "min_points": 20000, "max_points": 999999, "benefits": ["Sinrsiz gec cikis", "Suite yukseltme", "Ucretsiz spa", "Ozel karsilama", "VIP arac transferi"], "upgrade_eligible": True},
        ]
        for t in defaults:
            t["_id"] = str(uuid.uuid4())
            t["tenant_id"] = current_user.tenant_id
            await db.loyalty_tiers.insert_one(t)
            t["id"] = t.pop("_id")
        tiers = defaults
    else:
        for t in tiers:
            t["id"] = str(t.pop("_id"))
    return {"tiers": tiers}


@router.get("/pms/guest/{guest_id}/loyalty")
async def get_guest_loyalty(guest_id: str, current_user: User = Depends(get_current_user)):
    guest = await db.guests.find_one({"_id": guest_id, "tenant_id": current_user.tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    points = guest.get("loyalty_points", 0)
    stay_count = await db.bookings.count_documents({"guest_id": guest_id, "tenant_id": current_user.tenant_id, "status": "checked_out"})
    tiers = await db.loyalty_tiers.find({"tenant_id": current_user.tenant_id}).sort("min_points", 1).to_list(20)
    current_tier = "Silver"
    for t in tiers:
        if points >= t.get("min_points", 0):
            current_tier = t.get("name", "Silver")
    return {"guest_id": guest_id, "points": points, "tier": current_tier, "total_stays": stay_count}


@router.get("/pms/commission/export")
async def export_commission_report(start_date: str = None, end_date: str = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id, "commission_pct": {"$gt": 0}}
    if start_date:
        query["check_out"] = {"$gte": start_date}
    if end_date:
        query.setdefault("check_out", {})
        if isinstance(query["check_out"], dict):
            query["check_out"]["$lte"] = end_date
    bookings = await db.bookings.find(query).sort("check_out", -1).to_list(500)
    report = []
    for b in bookings:
        total = b.get("total_amount", 0) or 0
        pct = b.get("commission_pct", 0) or 0
        report.append({
            "booking_id": str(b.get("_id", "")),
            "guest_name": b.get("guest_name", ""),
            "agency": b.get("agency_name", b.get("channel", "")),
            "check_in": b.get("check_in", ""),
            "check_out": b.get("check_out", ""),
            "total_amount": total,
            "commission_pct": pct,
            "commission_amount": round(total * pct / 100, 2),
        })
    total_commission = sum(r["commission_amount"] for r in report)
    return {"report": report, "total_commission": total_commission, "booking_count": len(report)}


@router.get("/pms/group-blocks")
async def get_group_blocks(current_user: User = Depends(get_current_user)):
    docs = await db.group_blocks.find({"tenant_id": current_user.tenant_id}).sort("cutoff_date", 1).to_list(200)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"group_blocks": docs}


@router.post("/pms/group-blocks")
async def create_group_block(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "group_name": body.get("group_name", ""),
        "contact_name": body.get("contact_name", ""),
        "contact_email": body.get("contact_email", ""),
        "rooms_blocked": body.get("rooms_blocked", 0),
        "rooms_picked_up": 0,
        "room_type": body.get("room_type", ""),
        "rate": body.get("rate", 0),
        "check_in": body.get("check_in", ""),
        "check_out": body.get("check_out", ""),
        "cutoff_date": body.get("cutoff_date", ""),
        "status": "active",
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.group_blocks.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.post("/pms/group-blocks/{block_id}/cutoff")
async def process_group_cutoff(block_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    block = await db.group_blocks.find_one({"_id": block_id, "tenant_id": current_user.tenant_id})
    if not block:
        raise HTTPException(status_code=404, detail="Group block not found")
    rooms_blocked = block.get("rooms_blocked", 0)
    rooms_picked = block.get("rooms_picked_up", 0)
    rooms_released = rooms_blocked - rooms_picked
    now = datetime.utcnow()
    await db.group_blocks.update_one(
        {"_id": block_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "cutoff_processed",
            "rooms_released": rooms_released,
            "cutoff_processed_at": now.isoformat(),
            "cutoff_processed_by": current_user.email,
        }}
    )
    return {
        "block_id": block_id,
        "group_name": block.get("group_name", ""),
        "rooms_released": rooms_released,
        "rooms_picked_up": rooms_picked,
        "status": "cutoff_processed",
    }


@router.delete("/pms/group-blocks/{block_id}")
async def delete_group_block(block_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    result = await db.group_blocks.delete_one({"_id": block_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group block not found")
    return {"id": block_id, "status": "deleted"}
