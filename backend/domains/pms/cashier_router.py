import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api", tags=["PMS / Cashier"])


def _safe_float(val, default=0.0):
    try:
        return float(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid numeric value: {val}")


def _safe_int(val, default=0):
    try:
        return int(val or default)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid integer value: {val}")


@router.get("/cashier/current-shift")
async def get_current_shift(current_user: User = Depends(get_current_user)):
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"},
        sort=[("opened_at", -1)]
    )
    if shift:
        shift["id"] = str(shift.pop("_id"))
        txns = await db.cashier_transactions.find(
            {"tenant_id": current_user.tenant_id, "shift_id": shift["id"]}
        ).sort("created_at", -1).to_list(200)
        for t in txns:
            t["id"] = str(t.pop("_id"))
        return {"shift": shift, "transactions": txns}
    return {"shift": None, "transactions": []}


@router.post("/cashier/open-shift")
async def open_shift(body: dict = Body({}), current_user: User = Depends(get_current_user)):
    existing = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Zaten acik bir vardiya var")
    now = datetime.utcnow()
    opening_amount = _safe_float(body.get("opening_amount", 0))
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "cashier_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        "cashier_email": current_user.email,
        "opening_amount": opening_amount,
        "cash_in": 0,
        "cash_out": 0,
        "status": "open",
        "opened_at": now.isoformat(),
        "opened_by": current_user.email,
        "opened_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        "denominations": body.get("denomination_counts", body.get("denominations", {})),
    }
    await db.cashier_shifts.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return {"shift": doc}


@router.post("/cashier/close-shift")
async def close_shift(body: dict = Body({}), current_user: User = Depends(get_current_user)):
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if not shift:
        raise HTTPException(status_code=404, detail="Acik vardiya bulunamadi")
    now = datetime.utcnow()
    counted_amount = _safe_float(body.get("counted_amount", 0))
    expected = shift.get("opening_amount", 0) + shift.get("cash_in", 0) - shift.get("cash_out", 0)
    difference = counted_amount - expected
    await db.cashier_shifts.update_one(
        {"_id": shift["_id"], "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "closed",
            "closed_at": now.isoformat(),
            "closing_amount": counted_amount,
            "expected_amount": expected,
            "difference": difference,
            "closing_denominations": body.get("denomination_counts", body.get("denominations", {})),
            "closed_by": current_user.email,
            "closed_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
        }}
    )
    return {
        "status": "closed",
        "counted_amount": counted_amount,
        "expected_amount": expected,
        "difference": difference,
        "closed_at": now.isoformat(),
        "closed_by": current_user.email,
        "closed_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
    }


@router.post("/cashier/handover-shift")
async def handover_shift(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    shift = await db.cashier_shifts.find_one(
        {"tenant_id": current_user.tenant_id, "status": "open"}
    )
    if not shift:
        raise HTTPException(status_code=404, detail="Acik vardiya bulunamadi")
    target_email = body.get("target_email", "").strip()
    target_name = body.get("target_name", "").strip()
    if not target_email:
        raise HTTPException(status_code=400, detail="Devir yapilacak kullanici e-postasi gerekli")
    now = datetime.utcnow()
    counted_amount = _safe_float(body.get("counted_amount", 0))
    expected = shift.get("opening_amount", 0) + shift.get("cash_in", 0) - shift.get("cash_out", 0)
    difference = counted_amount - expected
    await db.cashier_shifts.update_one(
        {"_id": shift["_id"], "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": "handed_over",
            "closed_at": now.isoformat(),
            "closing_amount": counted_amount,
            "expected_amount": expected,
            "difference": difference,
            "closed_by": current_user.email,
            "closed_by_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
            "handover_to_email": target_email,
            "handover_to_name": target_name or target_email,
            "handover_at": now.isoformat(),
            "handover_note": body.get("note", ""),
        }}
    )
    new_doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "cashier_name": target_name or target_email,
        "cashier_email": target_email,
        "opening_amount": counted_amount,
        "cash_in": 0,
        "cash_out": 0,
        "status": "open",
        "opened_at": now.isoformat(),
        "opened_by": target_email,
        "opened_by_name": target_name or target_email,
        "previous_shift_id": str(shift["_id"]),
        "handover_from_email": current_user.email,
        "handover_from_name": current_user.name if hasattr(current_user, 'name') else current_user.email,
    }
    await db.cashier_shifts.insert_one(new_doc)
    new_doc["id"] = new_doc.pop("_id")
    return {
        "status": "handed_over",
        "previous_shift_closed": True,
        "new_shift": new_doc,
        "counted_amount": counted_amount,
        "difference": difference,
    }


@router.get("/cashier/shift-history")
async def shift_history(skip: int = 0, limit: int = 20, current_user: User = Depends(get_current_user)):
    cursor = db.cashier_shifts.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("opened_at", -1).skip(skip).limit(limit)
    shifts = await cursor.to_list(limit)
    for s in shifts:
        s["id"] = str(s.pop("_id"))
    total = await db.cashier_shifts.count_documents({"tenant_id": current_user.tenant_id})
    return {"shifts": shifts, "total": total}


@router.get("/laundry/orders")
async def get_laundry_orders(skip: int = 0, limit: int = 100, status: str = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    cursor = db.laundry_orders.find(query).sort("created_at", -1).skip(skip).limit(limit)
    orders = await cursor.to_list(limit)
    for o in orders:
        o["id"] = str(o.pop("_id"))
    return {"orders": orders}


@router.post("/laundry/orders")
async def create_laundry_order(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    if not body.get("room_number"):
        raise HTTPException(status_code=400, detail="Oda numarasi gerekli")
    if not body.get("items") or len(body["items"]) == 0:
        raise HTTPException(status_code=400, detail="En az bir urun gerekli")
    now = datetime.utcnow()
    total = sum(_safe_float(i.get("total", 0)) for i in body["items"])
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "room_number": body.get("room_number", ""),
        "guest_name": body.get("guest_name", ""),
        "service_type": body.get("service_type", "wash_iron"),
        "items": body.get("items", []),
        "total": total,
        "notes": body.get("notes", ""),
        "priority": body.get("priority", "normal"),
        "status": "pending",
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.laundry_orders.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.patch("/laundry/orders/{order_id}")
async def update_laundry_order(order_id: str, body: dict = Body(...), current_user: User = Depends(get_current_user)):
    update_fields = {k: v for k, v in body.items() if k not in ("id", "_id", "tenant_id")}
    update_fields["updated_at"] = datetime.utcnow().isoformat()
    result = await db.laundry_orders.update_one(
        {"_id": order_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi")
    return {"id": order_id, "status": update_fields.get("status", "updated")}


@router.delete("/laundry/orders/{order_id}")
async def delete_laundry_order(order_id: str, current_user: User = Depends(get_current_user)):
    result = await db.laundry_orders.delete_one(
        {"_id": order_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi")
    return {"id": order_id, "status": "deleted"}


@router.get("/meeting-rooms")
async def get_meeting_rooms(current_user: User = Depends(get_current_user)):
    rooms = await db.meeting_rooms.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("name", 1).to_list(100)
    for r in rooms:
        r["id"] = str(r.pop("_id"))
    if not rooms:
        defaults = [
            {"name": "Balo Salonu", "capacity": 500, "area": 800, "floor": "Zemin", "setup_types": ["theater", "banquet", "cocktail"], "equipment": ["Projektor", "Ses Sistemi", "Sahne"], "status": "available"},
            {"name": "Toplanti Salonu A", "capacity": 50, "area": 80, "floor": "1. Kat", "setup_types": ["classroom", "u_shape", "boardroom"], "equipment": ["Projektor", "Beyaz Perde", "Video Konferans"], "status": "available"},
            {"name": "Toplanti Salonu B", "capacity": 30, "area": 50, "floor": "1. Kat", "setup_types": ["classroom", "boardroom"], "equipment": ["LED Ekran", "Ses Sistemi"], "status": "available"},
            {"name": "VIP Toplanti Odasi", "capacity": 12, "area": 30, "floor": "2. Kat", "setup_types": ["boardroom"], "equipment": ["Video Konferans", "LED Ekran", "Ses Sistemi"], "status": "available"},
        ]
        for d in defaults:
            d["_id"] = str(uuid.uuid4())
            d["tenant_id"] = current_user.tenant_id
            await db.meeting_rooms.insert_one(d)
            d["id"] = d.pop("_id")
        rooms = defaults
    return {"rooms": rooms}


@router.get("/meeting-rooms/reservations")
async def get_meeting_reservations(skip: int = 0, limit: int = 50, current_user: User = Depends(get_current_user)):
    cursor = db.meeting_reservations.find(
        {"tenant_id": current_user.tenant_id}
    ).sort("date", -1).skip(skip).limit(limit)
    reservations = await cursor.to_list(limit)
    for r in reservations:
        r["id"] = str(r.pop("_id"))
    return {"reservations": reservations}


@router.post("/meeting-rooms/reservations")
async def create_meeting_reservation(body: dict = Body(...), current_user: User = Depends(get_current_user)):
    if not body.get("room_name") and not body.get("room_id"):
        raise HTTPException(status_code=400, detail="Salon secimi gerekli")
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "room_id": body.get("room_id", ""),
        "room_name": body.get("room_name", ""),
        "company_name": body.get("company_name", ""),
        "event_name": body.get("event_name", ""),
        "contact_name": body.get("contact_name", ""),
        "contact_phone": body.get("contact_phone", ""),
        "date": body.get("date", ""),
        "start_time": body.get("start_time", ""),
        "end_time": body.get("end_time", ""),
        "setup_type": body.get("setup_type", ""),
        "attendees": _safe_int(body.get("attendees", 0)),
        "status": "confirmed",
        "notes": body.get("notes", ""),
        "created_at": now.isoformat(),
        "created_by": current_user.email,
    }
    await db.meeting_reservations.insert_one(doc)
    doc["id"] = doc.pop("_id")
    return doc


@router.delete("/meeting-rooms/reservations/{reservation_id}")
async def delete_meeting_reservation(reservation_id: str, current_user: User = Depends(get_current_user)):
    result = await db.meeting_reservations.delete_one(
        {"_id": reservation_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    return {"id": reservation_id, "status": "deleted"}
