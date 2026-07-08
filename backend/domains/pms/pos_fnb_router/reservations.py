"""
reservations.py

Restaurant table management and reservation endpoints.
"""
from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v92

router = APIRouter(tags=["pos_reservations"])

class ReservationCreateRequest(BaseModel):
    outlet_id: str
    table_id: str
    guest_name: str
    pax: int
    res_date: str  # YYYY-MM-DD
    res_time: str  # HH:MM
    notes: str | None = None

@router.get("/pos/reservations")
async def get_reservations(
    outlet_id: str | None = None,
    res_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    """Get upcoming table reservations for the POS staff."""
    query = {"tenant_id": current_user.tenant_id}
    if outlet_id:
        query["outlet_id"] = outlet_id
    if res_date:
        query["res_date"] = res_date
        
    reservations = await db.pos_table_reservations.find(query, {"_id": 0}).sort("res_time", 1).to_list(100)
    return reservations

@router.post("/pos/reservations")
async def create_reservation(
    req: ReservationCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    """Create a new table reservation."""
    
    # Conflict check (Double-booking defense)
    conflict = await db.pos_table_reservations.find_one({
        "tenant_id": current_user.tenant_id,
        "outlet_id": req.outlet_id,
        "table_id": req.table_id,
        "res_date": req.res_date,
        "res_time": req.res_time,
        "status": {"$in": ["confirmed", "seated"]}
    })
    
    if conflict:
        raise HTTPException(status_code=400, detail="Masa bu saatte zaten dolu.")
        
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "outlet_id": req.outlet_id,
        "table_id": req.table_id,
        "guest_name": req.guest_name,
        "pax": req.pax,
        "res_date": req.res_date,
        "res_time": req.res_time,
        "notes": req.notes,
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id
    }
    
    await db.pos_table_reservations.insert_one(doc)
    
    doc.pop("_id", None)
    return doc

@router.put("/pos/reservations/{reservation_id}/status")
async def update_reservation_status(
    reservation_id: str,
    status: str,  # 'seated', 'cancelled', 'completed'
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    valid_statuses = ["confirmed", "seated", "completed", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Geçersiz rezervasyon durumu")
        
    updated = await db.pos_table_reservations.find_one_and_update(
        {"tenant_id": current_user.tenant_id, "id": reservation_id},
        {"$set": {"status": status, "updated_at": datetime.now(UTC).isoformat()}},
        return_document=True
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
        
    updated.pop("_id", None)
    return updated
