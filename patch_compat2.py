import re

with open('backend/routers/missing_endpoints_compat.py', 'r') as f:
    content = f.read()

# First replace the previous patch's insert with the full block
new_block = """    # Rezervasyonu oluştur
    try:
        await create_booking_atomic(tenant_id=current_user.tenant_id, booking_doc=booking_doc)
    except Exception as e:
        if "Conflict" in str(e) or "already booked" in str(e):
            raise HTTPException(status_code=409, detail=f"Oda müsait değil: {e}")
        raise HTTPException(status_code=500, detail=f"Rezervasyon oluşturulamadı: {e}")
        
    folio_id = str(uuid.uuid4())
    folio_doc = {
        "id": folio_id,
        "tenant_id": current_user.tenant_id,
        "booking_id": booking_id,
        "folio_number": f"F-{datetime.now(UTC).year}-{uuid.uuid4().hex[:5].upper()}",
        "folio_type": "guest",
        "guest_id": None,
        "status": "open",
        "balance": float(req.get("total_price", 0)),
        "total": float(req.get("total_price", 0)),
        "room_charge": float(req.get("total_price", 0)),
        "currency": req.get("currency", "TRY"),
        "created_at": now,
    }
    await db.folios.insert_one(folio_doc)
    
    await db.audit_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "action": "CREATE_BOOKING",
            "entity": "booking",
            "entity_id": booking_id,
            "actor_id": current_user.id,
            "created_at": now,
            "details": {"source": "agency_request", "request_id": request_id},
        }
    )
"""

content = re.sub(
    r'    await create_booking_atomic\(tenant_id=current_user\.tenant_id, booking_doc=booking_doc\)',
    new_block,
    content
)

with open('backend/routers/missing_endpoints_compat.py', 'w') as f:
    f.write(content)
