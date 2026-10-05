import re

with open('backend/routers/missing_endpoints_compat.py', 'r') as f:
    content = f.read()

if 'from core.atomic_booking import create_booking_atomic' not in content:
    content = content.replace('from pydantic import BaseModel, Field, field_validator', 'from pydantic import BaseModel, Field, field_validator\nfrom core.atomic_booking import create_booking_atomic')

content = re.sub(
    r'        "updated_at": now,\n    }\n    await db\.bookings\.insert_one\(booking_doc\)',
    '        "updated_at": now,\n    }\n    await create_booking_atomic(tenant_id=current_user.tenant_id, booking_doc=booking_doc)',
    content
)

# Also check for idempotency in approval
content = content.replace(
    '    if not req:\n        raise HTTPException(status_code=404, detail="Talep bulunamadi")\n    now = datetime.now(UTC).isoformat()',
    '    if not req:\n        raise HTTPException(status_code=404, detail="Talep bulunamadi")\n    if req.get("status") == "approved" and req.get("booking_id"):\n        return {"approved": True, "request_id": request_id, "booking_id": req.get("booking_id"), "message": "Zaten onaylanmis"}\n    now = datetime.now(UTC).isoformat()'
)

with open('backend/routers/missing_endpoints_compat.py', 'w') as f:
    f.write(content)
