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


_VALID_CONCIERGE_TYPES = {
    "restaurant", "transfer", "tour", "ticket", "spa",
    "valet", "parcel", "deposit_box", "wakeup", "other",
}
_VALID_CONCIERGE_STATUSES = {"pending", "in_progress", "completed", "cancelled", "confirmed"}
_VALID_PRIORITIES = {"normal", "high", "vip"}


async def _lookup_active_booking_for_room(tenant_id: str, room_number: str) -> dict | None:
    """Return the active (checked_in/in_house) booking for a room, with folio_id if any."""
    if not room_number:
        return None
    try:
        booking = await db.bookings.find_one({
            "tenant_id": tenant_id,
            "room_number": str(room_number),
            "status": {"$in": ["checked_in", "in_house"]},
        }, {"_id": 0})
    except Exception:
        return None
    if not booking:
        return None
    booking_id = booking.get("id") or booking.get("booking_id") or ""
    folio_id = ""
    if booking_id:
        try:
            folio = await db.folios.find_one(
                {"tenant_id": tenant_id, "booking_id": booking_id, "status": "open"},
                {"_id": 0, "id": 1, "folio_number": 1},
            )
            if folio:
                folio_id = folio.get("id") or ""
        except Exception:
            folio_id = ""
    return {
        "booking_id": booking_id,
        "guest_name": booking.get("guest_name") or booking.get("primary_guest_name") or "",
        "room_number": booking.get("room_number") or room_number,
        "folio_id": folio_id,
        "check_in": booking.get("check_in"),
        "check_out": booking.get("check_out"),
    }


@router.get("/concierge/active-room/{room_number}")
async def concierge_active_room_lookup(room_number: str, current_user: User = Depends(get_current_user)):
    """Look up the active in-house booking for a room number to autofill guest/folio."""
    info = await _lookup_active_booking_for_room(current_user.tenant_id, room_number.strip())
    if not info:
        return {"found": False}
    return {"found": True, **info}


@router.get("/concierge/requests")
async def get_concierge_requests(
    skip: int = 0, limit: int = 50,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query: dict = {"tenant_id": current_user.tenant_id}
    if status and status in _VALID_CONCIERGE_STATUSES:
        query["status"] = status
    safe_limit = max(1, min(int(limit or 50), 500))
    safe_skip = max(0, int(skip or 0))
    # Perf: find + count + aggregate sıralı (~3 RTT). Paralelize.
    import asyncio
    pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    _AGG_FAIL = object()
    async def _agg():
        try:
            return [row async for row in db.concierge_requests.aggregate(pipeline)]
        except Exception:
            return _AGG_FAIL
    docs, total, agg_rows = await asyncio.gather(
        db.concierge_requests.find(query).sort("created_at", -1).skip(safe_skip).limit(safe_limit).to_list(safe_limit),
        db.concierge_requests.count_documents(query),
        _agg(),
    )
    for d in docs:
        d["id"] = str(d.pop("_id"))
    counts = {"total": total, "pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
    # Aggregate başarısızsa count_documents'tan gelen `total`'ı koru (regression guard).
    if agg_rows is not _AGG_FAIL:
        for row in agg_rows:
            key = row.get("_id") or "pending"
            if key in counts:
                counts[key] = row.get("n", 0)
        counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return {"requests": docs, "total": total, "skip": safe_skip, "limit": safe_limit, "counts": counts}


@router.post("/concierge/requests")
async def create_concierge_request(body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    now = datetime.utcnow()
    req_type = (body.get("type") or "").strip()
    if req_type not in _VALID_CONCIERGE_TYPES:
        raise HTTPException(status_code=400, detail="Geçerli bir talep tipi seçin")
    room_number = (body.get("room_number") or "").strip()
    if not room_number:
        raise HTTPException(status_code=400, detail="Oda numarası zorunludur")
    priority = body.get("priority") or "normal"
    if priority not in _VALID_PRIORITIES:
        priority = "normal"
    pax = _safe_int(body.get("pax", 1), 1)
    if pax < 1:
        pax = 1
    amount = _safe_float(body.get("amount", 0), 0.0)
    if amount < 0:
        raise HTTPException(status_code=400, detail="Tutar negatif olamaz")
    currency = (body.get("currency") or "TRY").upper()[:8] or "TRY"
    charge_to_folio = bool(body.get("charge_to_folio") or False)

    # Cross-check active booking for the room (auto-fill missing guest/booking/folio)
    lookup = await _lookup_active_booking_for_room(current_user.tenant_id, room_number)
    booking_id = (body.get("booking_id") or (lookup or {}).get("booking_id") or "").strip()
    folio_id = (body.get("folio_id") or (lookup or {}).get("folio_id") or "").strip()
    guest_name = (body.get("guest_name") or "").strip() or ((lookup or {}).get("guest_name") or "")

    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "type": req_type,
        "room_number": room_number,
        "guest_name": guest_name,
        "details": (body.get("details") or "").strip(),
        "date": body.get("date") or now.strftime("%Y-%m-%d"),
        "time": body.get("time") or "",
        "pax": pax,
        "notes": (body.get("notes") or "").strip(),
        "priority": priority,
        "amount": amount,
        "currency": currency,
        "charge_to_folio": charge_to_folio,
        "booking_id": booking_id,
        "folio_id": folio_id,
        "folio_charge_id": "",
        "status": "pending",
        "created_at": now.isoformat(),
        "created_by": current_user.email,
        "room_match_found": bool(lookup),
    }
    await db.concierge_requests.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


_EDITABLE_CONCIERGE_FIELDS = {
    "type", "room_number", "guest_name", "details", "date", "time",
    "notes", "priority", "amount", "currency", "charge_to_folio",
    "booking_id", "folio_id",
}


async def _post_charge_to_folio(tenant_id: str, request_doc: dict, user_email: str) -> str | None:
    """Post a charge to the linked folio when completing a paid concierge request.
    Returns the new charge id, or None if no charge was posted."""
    amount = float(request_doc.get("amount") or 0)
    folio_id = request_doc.get("folio_id") or ""
    if amount <= 0 or not folio_id or not request_doc.get("charge_to_folio"):
        return None
    if request_doc.get("folio_charge_id"):
        # already charged; do not double-post
        return request_doc.get("folio_charge_id")
    try:
        from domains.pms.folio.services.folio_service import FolioService
        type_label = (request_doc.get("type") or "other").replace("_", " ").title()
        details = request_doc.get("details") or ""
        description = f"Concierge — {type_label}"
        if details:
            description = f"{description}: {details[:80]}"
        charge = await FolioService.post_charge(tenant_id, folio_id, {
            "amount": amount,
            "currency": request_doc.get("currency") or "TRY",
            "description": description,
            "category": "concierge",
            "source": "concierge_request",
            "concierge_request_id": request_doc.get("_id") or request_doc.get("id"),
            "posted_by": user_email,
        })
        return charge.get("id") if charge else None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Folyoya işlenemedi: {exc}") from exc


@router.patch("/concierge/requests/{request_id}")
async def update_concierge_request(request_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    existing = await db.concierge_requests.find_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")

    update_set: dict = {
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": current_user.email,
    }

    # Editable fields
    for field in _EDITABLE_CONCIERGE_FIELDS:
        if field not in body:
            continue
        value = body[field]
        if field == "type":
            if value not in _VALID_CONCIERGE_TYPES:
                raise HTTPException(status_code=400, detail="Geçerli bir talep tipi seçin")
        elif field == "room_number":
            value = (value or "").strip()
            if not value:
                raise HTTPException(status_code=400, detail="Oda numarası zorunludur")
        elif field == "priority":
            if value not in _VALID_PRIORITIES:
                value = "normal"
        elif field == "amount":
            value = _safe_float(value, 0.0)
            if value < 0:
                raise HTTPException(status_code=400, detail="Tutar negatif olamaz")
        elif field == "currency":
            value = (value or "TRY").upper()[:8] or "TRY"
        elif field == "charge_to_folio":
            value = bool(value)
        update_set[field] = value

    if "pax" in body:
        pax_val = _safe_int(body.get("pax", 1), 1)
        if pax_val < 1:
            pax_val = 1
        update_set["pax"] = pax_val

    # Status transition
    new_status = body.get("status")
    if new_status is not None:
        if new_status not in _VALID_CONCIERGE_STATUSES:
            raise HTTPException(status_code=400, detail="Geçersiz durum")
        update_set["status"] = new_status

    # Build merged doc to evaluate folio posting
    merged = {**existing, **update_set}

    if new_status == "completed":
        charge_id = await _post_charge_to_folio(current_user.tenant_id, merged, current_user.email)
        if charge_id:
            update_set["folio_charge_id"] = charge_id
            update_set["charged_at"] = datetime.utcnow().isoformat()

    await db.concierge_requests.update_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id},
        {"$set": update_set},
    )
    fresh = await db.concierge_requests.find_one(
        {"_id": request_id, "tenant_id": current_user.tenant_id}
    )
    if fresh:
        fresh["id"] = str(fresh.pop("_id"))
    return fresh or {"id": request_id, **update_set}


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
    # Perf: find + count sıralı (~2 RTT) → asyncio.gather.
    import asyncio
    docs, total = await asyncio.gather(
        db.kvkk_requests.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit),
        db.kvkk_requests.count_documents(query),
    )
    for d in docs:
        d["id"] = str(d.pop("_id"))
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


@router.post("/kvkk/consents/{consent_id}/revoke")
async def revoke_kvkk_consent(consent_id: str, body: dict = Body(default=None), current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # KVKK rıza geri çekme
):
    """KVKK rıza geri çekme (right to withdraw consent).

    Tenant-scoped: yalnız çağıranın tenant'ına ait rıza kaydını "revoked"
    işaretler + audit satırı yazar. Kayıt başka tenant'a aitse 404 (cross-tenant
    açığa çıkarma/mutasyon yok). `_id` (uuid-string) veya `id` alanı eşleşir.
    """
    body = body or {}
    reason = (body.get("reason") or "").strip()
    now = datetime.utcnow()
    result = await db.kvkk_consents.update_one(
        {"$or": [{"_id": consent_id}, {"id": consent_id}], "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "revoked",
            "revoked": True,
            "revoked_at": now.isoformat(),
            "revoked_by": current_user.email,
            "revoke_reason": reason,
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Consent not found")
    await db.kvkk_audit_log.insert_one({
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "action": "consent_revoked",
        "consent_id": consent_id,
        "reason": reason,
        "actor": current_user.email,
        "timestamp": now.isoformat(),
    })
    return {"id": consent_id, "status": "revoked"}


@router.get("/kvkk/export")
async def export_kvkk_data(guest_id: str | None = None, guest_name: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # KVKK veri erişim/taşınabilirlik
):
    """KVKK veri-sahibi erişim ihracı (right of access / data portability).

    Bir misafirin tenant-scoped KVKK ayak izini toplar: saklanan rızalar,
    veri-sahibi talepleri ve audit-log kayıtları. Selector (guest_id veya
    guest_name) verilmezse 400 — sınırsız tenant-genişliğinde döküm engellenir.
    Tüm sorgular `tenant_id` ile sınırlıdır (cross-tenant disclosure yok).
    """
    if not (guest_id or guest_name):
        raise HTTPException(status_code=400, detail="guest_id veya guest_name zorunludur")
    selectors = []
    if guest_id:
        selectors.append({"guest_id": guest_id})
    if guest_name:
        selectors.append({"guest_name": guest_name})
    sel = {"$or": selectors} if len(selectors) > 1 else selectors[0]
    query = {"tenant_id": current_user.tenant_id, **sel}
    consents = await db.kvkk_consents.find(query).sort("date", -1).to_list(500)
    requests_ = await db.kvkk_requests.find(query).sort("created_at", -1).to_list(500)
    audit = await db.kvkk_audit_log.find(query).sort("timestamp", -1).to_list(500)
    for coll in (consents, requests_, audit):
        for d in coll:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
    return {
        "guest_id": guest_id,
        "guest_name": guest_name,
        "tenant_id": current_user.tenant_id,
        "consents": consents,
        "requests": requests_,
        "audit_log": audit,
        "exported_at": datetime.utcnow().isoformat(),
        "counts": {
            "consents": len(consents),
            "requests": len(requests_),
            "audit_log": len(audit),
        },
    }


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

    # Encrypt PII (id_number) + _hash_ token before persistence. No name field
    # in update_fields -> existing doc not required.
    from security.guest_write import encrypt_guest_update
    update_fields = encrypt_guest_update(update_fields)
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
