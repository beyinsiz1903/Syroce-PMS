"""Room management: CRUD, types, stats, assign, auto-assign, release."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import require_admin, require_auth
from db import db
from helpers import create_audit_log
from room_assignment import (
    ROOM_STATUSES, ROOM_TYPES,
    assign_room, auto_assign_room, create_room, get_room, get_room_stats,
    list_rooms, release_room, update_room,
)
from schemas import AutoAssignRequest, RoomAssignRequest, RoomCreate, RoomUpdate

router = APIRouter()


@router.post("/api/rooms", tags=["Oda Yönetimi"], summary="Yeni oda oluştur")
async def create_new_room(req: RoomCreate, user=Depends(require_admin)):
    try:
        room = await create_room(
            db, room_number=req.room_number, room_type=req.room_type,
            floor=req.floor, capacity=req.capacity,
            property_id=req.property_id, features=req.features,
        )
        return {"success": True, "room": room}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/rooms", tags=["Oda Yönetimi"], summary="Odaları listele")
async def get_rooms(
    property_id: Optional[str] = None, status: Optional[str] = None,
    room_type: Optional[str] = None, floor: Optional[int] = None,
    user=Depends(require_auth),
):
    rooms = await list_rooms(db, property_id=property_id, status=status,
                             room_type=room_type, floor=floor)
    return {"rooms": rooms, "total": len(rooms)}


@router.get("/api/rooms/types", tags=["Oda Yönetimi"], summary="Oda tipleri")
async def get_room_types():
    return {"room_types": ROOM_TYPES, "statuses": ROOM_STATUSES}


@router.get("/api/rooms/stats", tags=["Oda Yönetimi"], summary="Oda istatistikleri")
async def get_rooms_stats(property_id: Optional[str] = None, user=Depends(require_auth)):
    return await get_room_stats(db, property_id=property_id)


@router.get("/api/rooms/{room_id}", tags=["Oda Yönetimi"], summary="Oda detayı")
async def get_room_detail(room_id: str, user=Depends(require_auth)):
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return {"room": room}


@router.patch("/api/rooms/{room_id}", tags=["Oda Yönetimi"], summary="Oda güncelle")
async def update_room_endpoint(room_id: str, req: RoomUpdate, user=Depends(require_admin)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    room = await update_room(db, room_id, updates)
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return {"success": True, "room": room}


@router.post("/api/rooms/assign", tags=["Oda Yönetimi"], summary="Oda ata",
             description="Belirtilen misafire oda atar")
async def assign_room_endpoint(req: RoomAssignRequest, user=Depends(require_auth)):
    try:
        result = await assign_room(db, room_id=req.room_id, guest_id=req.guest_id)
        room_data = result.get("room", {})
        assignment_data = result.get("assignment", {})
        await create_audit_log(req.guest_id, "room_assigned",
                               metadata={"room_id": req.room_id, "room_number": room_data.get("room_number", "")},
                               user_email=user.get("email"))
        return {"success": True, "room": room_data, "assignment": assignment_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Oda atama hatası: {str(e)}")


@router.post("/api/rooms/auto-assign", tags=["Oda Yönetimi"], summary="Otomatik oda ata",
             description="Scan sonrası müsait odayı otomatik atar")
async def auto_assign_room_endpoint(req: AutoAssignRequest, user=Depends(require_auth)):
    try:
        result = await auto_assign_room(db, guest_id=req.guest_id,
                                         property_id=req.property_id,
                                         preferred_type=req.preferred_type)
        if not result:
            raise HTTPException(status_code=404, detail="Müsait oda bulunamadı")
        room_data = result.get("room", {})
        assignment_data = result.get("assignment", {})
        await create_audit_log(req.guest_id, "room_auto_assigned",
                               metadata={"room_id": room_data.get("room_id", ""), "room_number": room_data.get("room_number", "")},
                               user_email=user.get("email"))
        return {"success": True, "room": room_data, "assignment": assignment_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Otomatik oda atama hatası: {str(e)}")


@router.post("/api/rooms/{room_id}/release", tags=["Oda Yönetimi"], summary="Odayı serbest bırak")
async def release_room_endpoint(room_id: str, guest_id: Optional[str] = None, user=Depends(require_auth)):
    try:
        room = await release_room(db, room_id=room_id, guest_id=guest_id)
        return {"success": True, "room": room}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
