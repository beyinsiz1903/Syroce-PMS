"""
spa_gym.py

SPA & Gym management endpoints mapped to the POS subsystem.
Includes resources (therapists, cabins), memberships, and reservations.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v92

router = APIRouter(tags=["pos_spa_gym"])

# --- Models ---

class SpaResourceCreateRequest(BaseModel):
    name: str
    type: str  # e.g., 'therapist', 'cabin', 'trainer'
    status: str = "active"

class SpaMembershipCreateRequest(BaseModel):
    guest_name: str
    membership_type: str  # e.g., 'monthly_gym', 'annual_spa'
    start_date: str
    end_date: str
    price: float
    status: str = "active"

class SpaReservationCreateRequest(BaseModel):
    guest_name: str
    service_item_id: str  # links to pos_menu_items
    therapist_id: str | None = None
    cabin_id: str | None = None
    res_date: str
    res_time: str
    duration_minutes: int = 60
    notes: str | None = None


# --- Resources ---

@router.get("/pos/spa/resources")
async def get_spa_resources(
    resource_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    """List SPA/Gym resources (therapists, cabins, etc.)"""
    query = {"tenant_id": current_user.tenant_id}
    if resource_type:
        query["type"] = resource_type

    resources = await db.pos_spa_resources.find(query, {"_id": 0}).to_list(100)
    return resources

@router.post("/pos/spa/resources")
async def create_spa_resource(
    req: SpaResourceCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "name": req.name,
        "type": req.type,
        "status": req.status,
        "created_at": datetime.now(UTC).isoformat()
    }
    await db.pos_spa_resources.insert_one(doc)
    doc.pop("_id", None)
    return doc


# --- Memberships ---

@router.get("/pos/spa/memberships")
async def get_spa_memberships(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status

    memberships = await db.pos_spa_memberships.find(query, {"_id": 0}).to_list(100)
    return memberships

@router.post("/pos/spa/memberships")
async def create_spa_membership(
    req: SpaMembershipCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_name": req.guest_name,
        "membership_type": req.membership_type,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "price": req.price,
        "status": req.status,
        "created_at": datetime.now(UTC).isoformat()
    }
    await db.pos_spa_memberships.insert_one(doc)
    doc.pop("_id", None)
    return doc


# --- Reservations ---

@router.get("/pos/spa/reservations")
async def get_spa_reservations(
    res_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    query = {"tenant_id": current_user.tenant_id}
    if res_date:
        query["res_date"] = res_date

    reservations = await db.pos_spa_reservations.find(query, {"_id": 0}).sort("res_time", 1).to_list(200)
    return reservations

@router.post("/pos/spa/reservations")
async def create_spa_reservation(
    req: SpaReservationCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    """Create a SPA reservation, ensuring the therapist or cabin isn't double-booked."""

    # Double-booking check
    conflict_query = {
        "tenant_id": current_user.tenant_id,
        "res_date": req.res_date,
        "res_time": req.res_time,
        "status": {"$in": ["confirmed", "in_progress"]}
    }

    if req.therapist_id or req.cabin_id:
        or_conditions = []
        if req.therapist_id:
            or_conditions.append({"therapist_id": req.therapist_id})
        if req.cabin_id:
            or_conditions.append({"cabin_id": req.cabin_id})
        conflict_query["$or"] = or_conditions

        conflict = await db.pos_spa_reservations.find_one(conflict_query)
        if conflict:
            raise HTTPException(status_code=400, detail="Terapist veya kabin bu saatte dolu.")

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "guest_name": req.guest_name,
        "service_item_id": req.service_item_id,
        "therapist_id": req.therapist_id,
        "cabin_id": req.cabin_id,
        "res_date": req.res_date,
        "res_time": req.res_time,
        "duration_minutes": req.duration_minutes,
        "notes": req.notes,
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id
    }

    await db.pos_spa_reservations.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/pos/spa/reservations/{reservation_id}/status")
async def update_spa_reservation_status(
    reservation_id: str,
    status: str,  # 'in_progress', 'completed', 'cancelled', 'no_show'
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    valid_statuses = ["confirmed", "in_progress", "completed", "cancelled", "no_show"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Geçersiz durum")

    updated = await db.pos_spa_reservations.find_one_and_update(
        {"tenant_id": current_user.tenant_id, "id": reservation_id},
        {"$set": {"status": status, "updated_at": datetime.now(UTC).isoformat()}},
        return_document=True
    )

    if not updated:
        raise HTTPException(status_code=404, detail="SPA rezervasyonu bulunamadı")

    updated.pop("_id", None)
    return updated

@router.post("/pos/spa/reservations/{reservation_id}/charge")
async def charge_spa_reservation(
    reservation_id: str,
    folio_id: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v92("pos"))
):
    """
    Charges a completed SPA reservation to a folio, simulating POS Folio transfer.
    """
    reservation = await db.pos_spa_reservations.find_one({
        "tenant_id": current_user.tenant_id,
        "id": reservation_id
    })

    if not reservation:
        raise HTTPException(status_code=404, detail="SPA rezervasyonu bulunamadı")

    if reservation.get("status") != "completed":
        # Automatically complete it before charging
        await db.pos_spa_reservations.update_one(
            {"id": reservation_id},
            {"$set": {"status": "completed", "charged": True}}
        )

    # In a real system, we'd look up the `service_item_id` in `pos_menu_items`
    # and call `postOrderToFolio` or directly write a transaction.
    # For now, mark it charged.
    return {"success": True, "message": "SPA hizmet bedeli yansıtıldı.", "folio_id": folio_id}

