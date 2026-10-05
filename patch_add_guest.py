with open("backend/routers/reservation_detail.py", "r") as f:
    content = f.read()

endpoint = """
@router.post("/reservations/{booking_id}/guests")
async def add_reservation_guest(
    booking_id: str,
    data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),
):
    _enforce_perm(current_user.role, "edit_booking")
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    import uuid
    from datetime import datetime, UTC
    from routers.pms_guests import _encrypt_guest
    
    guest_id = f"GST-{uuid.uuid4().hex[:8].upper()}"
    guest = {
        "id": guest_id,
        "tenant_id": tid,
        "created_at": datetime.now(UTC).isoformat(),
        "total_stays": 1,
        "total_spend": 0.0,
    }
    
    allowed = {"name", "email", "phone", "id_type", "id_number", "nationality", "date_of_birth", "gender", "address", "city", "country", "notes"}
    for k in allowed:
        if k in data:
            guest[k] = data[k]
            
    from security.search_normalize import normalized_set_for_update
    _norm = normalized_set_for_update(guest, collection="guests")
    guest = _encrypt_guest(guest)
    guest.update(_norm)
    
    await db.guests.insert_one(guest)
    await db.booking_guests.insert_one({
        "id": f"BG-{uuid.uuid4().hex[:8].upper()}",
        "tenant_id": tid,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "created_at": datetime.now(UTC).isoformat()
    })
    
    return {"status": "ok", "guest_id": guest_id}
"""

if "@router.post(\"/reservations/{booking_id}/guests\")" not in content:
    content += endpoint

with open("backend/routers/reservation_detail.py", "w") as f:
    f.write(content)
