"""
PMS Services Router — Operational service endpoints.
Extracted from pms.py (Stage 3a).

Routes:
  GET  /pms/room-services
  PUT  /pms/room-services/{service_id}
  GET  /pms/staff-tasks
  POST /pms/staff-tasks
  PUT  /pms/staff-tasks/{task_id}
  GET  /pms/allotment-contracts
  POST /pms/allotment-contracts
  POST /pms/allotment-contracts/{contract_id}/release
  GET  /pms/group-reservations
  POST /pms/group-reservations
  GET  /pms/setup-status
"""

import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from models.schemas import User
from modules.pms_core.allotment_usage import available_rooms, contract_usage
from modules.pms_core.module_scope_service import require_module_scope
from modules.pms_core.role_permission_service import (
    require_module_role,  # v101 DW
    require_op,  # v101 DW
)
from modules.pms_core.stay_night_metrics import is_physical_room

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["pms-services"])


# ═══════════════════════════════════════════════════════════════════
# Room Services
# ═══════════════════════════════════════════════════════════════════


# rbac-allow: cache-rbac — oda servis kayıtları operasyonel (FO/HK/restoran/manager/admin)
@router.get("/pms/room-services")
@cached(ttl=300, key_prefix="pms_room_services")  # Cache for 5 min
async def get_hotel_room_services(current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return services


_ROOM_SERVICE_UPDATE_ALLOWED = {
    "service_type",
    "description",
    "status",
    "priority",
    "assigned_to",
    "scheduled_at",
    "completed_at",
    "notes",
    "amount",
    "quantity",
    "room_id",
    "guest_id",
    "metadata",
}


@router.put("/pms/room-services/{service_id}")
async def update_room_service(
    service_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_role("frontdesk")),  # v101 DW
):
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="Gecersiz guncelleme verisi")
    safe = {k: v for k, v in updates.items() if k in _ROOM_SERVICE_UPDATE_ALLOWED}
    if not safe:
        raise HTTPException(status_code=400, detail="Guncellenecek izinli alan yok")
    if safe.get("status") == "completed":
        safe["completed_at"] = datetime.now(UTC).isoformat()
    await db.room_services.update_one({"id": service_id, "tenant_id": current_user.tenant_id}, {"$set": safe})
    service = await db.room_services.find_one({"id": service_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not service:
        raise HTTPException(status_code=404, detail="Hizmet bulunamadi")
    return service


# ═══════════════════════════════════════════════════════════════════
# Staff Tasks
# ═══════════════════════════════════════════════════════════════════


@router.get("/pms/staff-tasks")
async def get_staff_tasks(
    department: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    _module=Depends(require_module_scope("tasks")),
):
    """Get manual tasks and the idempotent projection of every QR request."""
    if page < 1 or not 1 <= page_size <= 200:
        raise HTTPException(400, "Invalid pagination")
    from domains.guest.qr_task_projection import reconcile_tenant_requests

    # Covers both current structured QR requests and historical legacy
    # requests. Upserts are deterministic, so loading the page never creates
    # duplicate tasks.
    await reconcile_tenant_requests(current_user.tenant_id)
    query = {"tenant_id": current_user.tenant_id}
    if department:
        query["department"] = department
    if status:
        query["status"] = status

    total = await db.staff_tasks.count_documents(query)
    skip = (page - 1) * page_size
    tasks = await db.staff_tasks.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return {"tasks": tasks, "total": total, "page": page, "page_size": page_size}


@router.post("/pms/staff-tasks")
async def create_staff_task(
    task_data: dict,
    current_user: User = Depends(get_current_user),
    _module=Depends(require_module_scope("tasks")),
):
    """Create a new staff task. title ve room_id zorunlu — boş kayıt üretilmez."""
    raw_title = task_data.get("title")
    raw_room = task_data.get("room_id")
    title = (str(raw_title) if raw_title is not None else "").strip()
    room_id = (str(raw_room) if raw_room is not None else "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="title en az 3 karakter olmalı")
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id zorunludur")

    task = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "task_type": task_data.get("task_type", "maintenance"),
        "department": task_data.get("department", "engineering"),
        "title": title,
        "room_id": room_id,
        "priority": task_data.get("priority", "normal"),
        "description": (task_data.get("description") or "").strip() or None,
        "assigned_to": (task_data.get("assigned_to") or "").strip() or None,
        "status": task_data.get("status", "pending"),
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }

    room = await db.rooms.find_one({"$or": [{"id": room_id}, {"room_number": room_id}], "tenant_id": current_user.tenant_id}, {"_id": 0, "room_number": 1, "id": 1})
    if not room:
        raise HTTPException(status_code=400, detail=f"Oda bulunamadı: {room_id}")
    task["room_id"] = room["id"]
    task["room_number"] = room["room_number"]

    await db.staff_tasks.insert_one(task)

    return {
        "id": task["id"],
        "tenant_id": task["tenant_id"],
        "task_type": task["task_type"],
        "department": task["department"],
        "title": task["title"],
        "room_id": task["room_id"],
        "room_number": task.get("room_number"),
        "priority": task["priority"],
        "description": task.get("description"),
        "assigned_to": task.get("assigned_to"),
        "status": task["status"],
        "created_by": task["created_by"],
        "created_at": task["created_at"],
    }


@router.delete("/pms/staff-tasks/cleanup-empty")
async def cleanup_empty_staff_tasks(
    current_user: User = Depends(get_current_user),
    _module=Depends(require_module_scope("tasks")),
):
    """Boş/geçersiz görevleri toplu sil (title yok veya 'x' gibi tek karakter)."""
    result = await db.staff_tasks.delete_many(
        {
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"title": {"$exists": False}},
                {"title": None},
                {"title": ""},
                {"title": {"$regex": r"^.{0,2}$"}},
                {"title": "Staff Task"},
            ],
        }
    )
    return {"deleted_count": result.deleted_count}


@router.put("/pms/staff-tasks/{task_id}")
async def update_staff_task(
    task_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user),
    _module=Depends(require_module_scope("tasks")),
):
    """Update a task and synchronize QR-originated work back to the guest."""
    task = await db.staff_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    allowed = {"status", "assigned_to", "priority", "resolution_note"}
    safe = {key: value for key, value in update_data.items() if key in allowed}
    if not safe:
        raise HTTPException(status_code=400, detail="Güncellenecek izinli alan yok")
    if "status" in safe and safe["status"] not in {"pending", "in_progress", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Geçersiz görev durumu")
    if "priority" in safe and safe["priority"] not in {"urgent", "high", "normal", "low"}:
        raise HTTPException(status_code=400, detail="Geçersiz öncelik")
    if "resolution_note" in safe:
        safe["resolution_note"] = str(safe["resolution_note"] or "").strip()[:2000]
    safe["updated_at"] = datetime.now(UTC).isoformat()

    if task.get("source") == "guest_qr":
        if safe.get("status") == "completed" and not (safe.get("resolution_note") or task.get("resolution_note")):
            raise HTTPException(
                status_code=400,
                detail="Misafir talebi sonuçlandırılırken çözüm bilgisi zorunludur",
            )
        from domains.guest.qr_task_projection import update_qr_task

        actor_name = getattr(current_user, "name", None) or getattr(current_user, "email", None) or "Personel"
        try:
            projected = await update_qr_task(
                task,
                safe,
                actor_id=current_user.id,
                actor_name=actor_name,
            )
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        safe.update({key: projected.get(key) for key in ("status", "assigned_to", "priority", "completed_at")})

    await db.staff_tasks.update_one(
        {"id": task_id, "tenant_id": current_user.tenant_id},
        {"$set": safe},
    )
    updated_task = await db.staff_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    return updated_task


@router.delete("/pms/staff-tasks/{task_id}")
async def delete_staff_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    _module=Depends(require_module_scope("tasks")),
):
    task = await db.staff_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "source": 1})
    if task and task.get("source") == "guest_qr":
        raise HTTPException(status_code=409, detail="Misafir talepleri denetim kaydı olduğu için silinemez")
    result = await db.staff_tasks.delete_one({"id": task_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Staff task deleted"}


# ═══════════════════════════════════════════════════════════════════
# Allotment Contracts
# ═══════════════════════════════════════════════════════════════════


@router.get("/pms/allotment-contracts")
async def get_allotment_contracts(page: int = 1, page_size: int = 50, current_user: User = Depends(get_current_user)):
    """Get tour operator allotment contracts with dynamic usage count.

    `used_rooms` is calculated by matching active bookings to the contract via:
      - room_type matches contract.room_type
      - check-in/out overlaps contract date range
      - status is active (pending/confirmed/guaranteed/checked_in)
      - tour_operator name matches one of the booking's agency/channel fields
        (agency_name, channel_display, channel, source_channel, ota_channel)
        OR the booking is explicitly linked via allotment_contract_id.
    Also returns `total_revenue` and `bookings_count` for reporting.
    """
    if page < 1 or not 1 <= page_size <= 200:
        raise HTTPException(400, "Invalid pagination")
    query = {"tenant_id": current_user.tenant_id}
    total = await db.allotment_contracts.count_documents(query)
    skip = (page - 1) * page_size
    contracts = await db.allotment_contracts.find(query, {"_id": 0}).skip(skip).limit(page_size).to_list(page_size)

    for contract in contracts:
        contract.update(await _allotment_usage(contract, current_user.tenant_id))
        contract["available_rooms"] = available_rooms(contract, contract["used_rooms"])

    return {"contracts": contracts, "total": total, "page": page, "page_size": page_size}


async def _allotment_usage(contract, tenant_id):
    rooms = await db.rooms.find({"tenant_id": tenant_id, "room_type": contract.get("room_type")}, {"_id": 0}).to_list(None)
    ids = [room["id"] for room in rooms if room.get("id") and is_physical_room(room)]
    bookings = await db.bookings.find({"tenant_id": tenant_id, "$or": [
        {"room_id": {"$in": ids}},
        {"allotment_contract_id": contract.get("id"), "room_id": {"$in": [None, ""]}},
        {"room_type": contract.get("room_type"), "room_id": {"$in": [None, ""]}},
    ]}, {"_id": 0}).to_list(None)
    for booking in bookings:
        if (not booking.get("room_id") and booking.get("allotment_contract_id") == contract.get("id")
                and booking.get("status") in {"pending", "confirmed", "guaranteed", "checked_in", "in_house"}
                and booking.get("room_type") != contract.get("room_type")):
            raise HTTPException(409, "Unassigned linked booking room type needs review before release")
    return contract_usage(contract, bookings)


def _validated_contract(data):
    operator, room_type = data.get("tour_operator"), data.get("room_type")
    if not isinstance(operator, str) or not 1 <= len(operator.strip()) <= 200:
        raise HTTPException(400, "Tour operator is required (1–200 characters)")
    if not isinstance(room_type, str) or not room_type.strip():
        raise HTTPException(400, "Room type is required")
    count, release = data.get("allocated_rooms"), data.get("release_days", 7)
    if type(count) is not int or not 1 <= count <= 10000 or type(release) is not int or not 0 <= release <= 365:
        raise HTTPException(400, "Room count and release days must be valid whole numbers")
    try:
        start, end = date.fromisoformat(data["start_date"]), date.fromisoformat(data["end_date"])
        rate = Decimal(str(data.get("rate")))
        if end <= start or not rate.is_finite() or rate < 0 or not math.isfinite(float(rate)):
            raise ValueError
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise HTTPException(400, "Invalid date range or nightly rate") from None
    currency = data.get("currency")
    if currency is not None and (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha()):
        raise HTTPException(400, "Currency must be a three-letter code")
    return {"tour_operator": operator.strip(), "room_type": room_type.strip(), "allocated_rooms": count,
            "release_days": release, "start_date": start.isoformat(), "end_date": end.isoformat(), "rate": float(rate)}


@router.post("/pms/allotment-contracts")
async def create_allotment_contract(
    contract_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create new allotment contract"""
    validated = _validated_contract(contract_data)
    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id, "room_type": validated["room_type"]}, {"_id": 0}).to_list(None)
    if not any(is_physical_room(room) for room in rooms):
        raise HTTPException(400, "Room type is not in this property's physical inventory")
    currency = contract_data.get("currency") or (await get_tenant_currency(current_user.tenant_id))[0]
    contract = {
        **validated,
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "used_rooms": 0,
        "currency": currency.upper(),
        "status": "active",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    await db.allotment_contracts.insert_one(contract)
    contract.pop("_id", None)
    return contract


@router.post("/pms/allotment-contracts/{contract_id}/release")
async def release_allotment_rooms(
    contract_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Release unused allotment rooms back to inventory"""
    contract = await db.allotment_contracts.find_one({"id": contract_id, "tenant_id": current_user.tenant_id})

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    usage = await _allotment_usage(contract, current_user.tenant_id)
    available = available_rooms(contract, usage["used_rooms"])
    if available:
        # Compare-and-set prevents repeated/concurrent release clicks from adding twice.
        query = {"id": contract_id, "tenant_id": current_user.tenant_id, "released_rooms": contract.get("released_rooms")}
        result = await db.allotment_contracts.update_one(query, {"$set": {
            "released_rooms": int(contract.get("released_rooms") or 0) + available,
            "released_at": datetime.now(UTC).isoformat(), "released_by": current_user.id,
        }})
        if result.matched_count == 0:
            raise HTTPException(409, "Contract changed; reload before release")
    return {"message": f"Released {available} internal contract rooms; no channel stock sent", "released_rooms": available,
            "used_rooms": usage["used_rooms"], "channel_inventory_changed": False}


@router.delete("/pms/allotment-contracts/{contract_id}")
async def delete_allotment_contract(
    contract_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    result = await db.allotment_contracts.delete_one({"id": contract_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contract not found")
    return {"success": True, "message": "Allotment contract deleted"}


# ═══════════════════════════════════════════════════════════════════
# Group Reservations
# ═══════════════════════════════════════════════════════════════════


@router.get("/pms/group-reservations")
async def get_group_reservations(page: int = 1, page_size: int = 50, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    total = await db.group_reservations.count_documents(query)
    skip = (page - 1) * page_size
    groups = await db.group_reservations.find(query, {"_id": 0}).skip(skip).limit(page_size).to_list(page_size)
    return {"groups": groups, "total": total, "page": page, "page_size": page_size}


@router.post("/pms/group-reservations")
async def create_group_reservation(
    group_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_role("frontdesk")),  # v101 DW
):
    from core.helpers import strip_reserved

    group_data = strip_reserved(group_data)
    group = {"id": str(uuid.uuid4()), "tenant_id": current_user.tenant_id, **group_data, "created_at": datetime.now(UTC).isoformat()}
    await db.group_reservations.insert_one(group)
    group.pop("_id", None)
    return group


@router.delete("/pms/group-reservations/{group_id}")
async def delete_group_reservation(
    group_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_role("frontdesk")),  # v101 DW
):
    result = await db.group_reservations.delete_one({"id": group_id, "tenant_id": current_user.tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group reservation not found")
    return {"success": True, "message": "Group reservation deleted"}


# ═══════════════════════════════════════════════════════════════════
# Setup Status
# ═══════════════════════════════════════════════════════════════════


@router.get("/pms/setup-status")
async def pms_setup_status(current_user: User = Depends(get_current_user)):
    """Return minimal setup status for PMS Lite onboarding (rooms/bookings counts)."""
    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})
    return {"rooms_count": rooms_count, "bookings_count": bookings_count}
