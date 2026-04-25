"""
HotelRunner Router — Room Mapping Endpoints
============================================

Pure CRUD over `hotelrunner_room_mappings` collection. No provider HTTP egress.
Mounted under the main `/api/channel-manager/hotelrunner` prefix by the
parent router.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

from .router_schemas import HRRoomMapping

router = APIRouter()


@router.post("/room-mappings")
async def create_room_mapping(
    payload: HRRoomMapping,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Create a PMS <> HotelRunner room mapping."""
    existing = await db.hotelrunner_room_mappings.find_one({
        "tenant_id": current_user.tenant_id,
        "hr_inv_code": payload.hr_inv_code,
        "hr_rate_code": payload.hr_rate_code,
    })
    if existing:
        await db.hotelrunner_room_mappings.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "pms_room_type": payload.pms_room_type,
                "hr_room_name": payload.hr_room_name,
                "sync_availability": payload.sync_availability,
                "sync_price": payload.sync_price,
                "sync_restrictions": payload.sync_restrictions,
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": current_user.name,
            }},
        )
        return {"message": "Oda eslemesi guncellendi", "mapping_id": existing.get("id")}

    mapping = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "pms_room_type": payload.pms_room_type,
        "hr_inv_code": payload.hr_inv_code,
        "hr_rate_code": payload.hr_rate_code,
        "hr_room_name": payload.hr_room_name,
        "sync_availability": payload.sync_availability,
        "sync_price": payload.sync_price,
        "sync_restrictions": payload.sync_restrictions,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }

    await db.hotelrunner_room_mappings.insert_one(mapping)
    mapping.pop("_id", None)
    return {"message": "Oda eslemesi olusturuldu", "mapping": mapping}


@router.post("/room-mappings/bulk")
async def bulk_create_room_mappings(
    mappings_data: list[HRRoomMapping],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Create or update multiple room mappings at once."""
    created = 0
    updated = 0
    for m in mappings_data:
        existing = await db.hotelrunner_room_mappings.find_one({
            "tenant_id": current_user.tenant_id,
            "hr_inv_code": m.hr_inv_code,
            "hr_rate_code": m.hr_rate_code,
        })
        if existing:
            await db.hotelrunner_room_mappings.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "pms_room_type": m.pms_room_type,
                    "hr_room_name": m.hr_room_name,
                    "sync_availability": m.sync_availability,
                    "sync_price": m.sync_price,
                    "sync_restrictions": m.sync_restrictions,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "updated_by": current_user.name,
                }},
            )
            updated += 1
        else:
            doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "pms_room_type": m.pms_room_type,
                "hr_inv_code": m.hr_inv_code,
                "hr_rate_code": m.hr_rate_code,
                "hr_room_name": m.hr_room_name,
                "sync_availability": m.sync_availability,
                "sync_price": m.sync_price,
                "sync_restrictions": m.sync_restrictions,
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": current_user.name,
            }
            await db.hotelrunner_room_mappings.insert_one(doc)
            created += 1

    return {"message": f"{created} yeni, {updated} guncellenen esleme", "created": created, "updated": updated}


@router.get("/room-mappings")
async def get_room_mappings(current_user: User = Depends(get_current_user)):
    """Get all PMS <> HotelRunner room mappings."""
    mappings = await db.hotelrunner_room_mappings.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(100)
    return {"mappings": mappings, "count": len(mappings)}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Delete a room mapping."""
    result = await db.hotelrunner_room_mappings.delete_one({
        "id": mapping_id,
        "tenant_id": current_user.tenant_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Esleme bulunamadi")
    return {"message": "Esleme silindi"}
