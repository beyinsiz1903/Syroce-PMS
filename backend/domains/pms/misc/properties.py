"""Auto-split from misc_router.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from models.schemas import CreatePropertyRequest, User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

sub_router = APIRouter()


@sub_router.post("/multi-property/properties")
async def create_property(
    request: CreatePropertyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Add new property to portfolio"""
    property_obj = {
        "id": str(uuid.uuid4()),
        "portfolio_id": current_user.tenant_id,
        "property_name": request.property_name,
        "property_code": request.property_code,
        "location": request.location,
        "total_rooms": request.total_rooms,
        "property_type": request.property_type,
        "status": request.status,
        "created_at": datetime.now(UTC).isoformat(),
    }

    property_copy = property_obj.copy()
    await db.properties.insert_one(property_copy)
    return property_obj


@sub_router.get("/multi-property/consolidated-report")
async def get_consolidated_report(start_date: str, end_date: str, metric: str = "occupancy", current_user: User = Depends(get_current_user)):
    """Get consolidated report across properties"""
    properties = await db.properties.find({"portfolio_id": current_user.tenant_id, "status": "active"}, {"_id": 0}).to_list(100)

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1

    report_data = []

    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()

        day_data = {"date": current_date, "properties": []}

        for prop in properties:
            # Simplified metrics
            if metric == "occupancy":
                rooms = await db.rooms.count_documents({"tenant_id": prop["id"]})
                occupied = await db.rooms.count_documents({"tenant_id": prop["id"], "room_status": "occupied"})
                value = (occupied / rooms * 100) if rooms > 0 else 0
            elif metric == "revenue":
                pipeline = [{"$match": {"tenant_id": prop["id"], "charge_date": current_date, "voided": False}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
                result = await db.folio_charges.aggregate(pipeline).to_list(1)
                value = result[0]["total"] if result else 0.0
            else:
                value = 0

            day_data["properties"].append({"property_id": prop["id"], "property_name": prop["property_name"], "value": round(value, 2)})

        report_data.append(day_data)

    return {"start_date": start_date, "end_date": end_date, "metric": metric, "data": report_data}


@sub_router.get("/properties/quick-list")
async def get_quick_property_list(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get quick property list for fast switching
    Returns only essential information for performance
    """
    current_user = await get_current_user(credentials)

    # Get all properties for this tenant
    properties = []
    async for prop in db.properties.find({"tenant_id": current_user.tenant_id}):
        properties.append(
            {
                "id": prop.get("id", str(uuid.uuid4())),
                "property_id": prop.get("property_id", prop.get("id")),
                "name": prop.get("name", prop.get("property_name", "Unnamed Property")),
                "location": prop.get("location", prop.get("city", "Unknown")),
                "type": prop.get("type", prop.get("property_type", "hotel")),
                "logo": prop.get("logo", ""),
                "is_active": prop.get("is_active", True),
                "room_count": prop.get("room_count", 0),
            }
        )

    # If no legacy properties exist, return the caller's real tenant instead of
    # fabricated hotels. Chain members are followed from /multi-property;
    # this switcher intentionally does not mint cross-tenant write access.
    if len(properties) == 0:
        from core.tenant_db import get_system_db

        tenant = await get_system_db().tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
        if tenant:
            properties = [{
                "id": tenant["id"],
                "property_id": tenant["id"],
                "name": tenant.get("property_name") or tenant["id"],
                "location": tenant.get("location") or "",
                "type": tenant.get("property_type") or "hotel",
                "logo": "",
                "is_active": tenant.get("subscription_status", "active") == "active",
                "room_count": int(tenant.get("total_rooms") or 0),
                "is_current_tenant": True,
            }]

    # Get user's current property
    current_property_id = current_user.property_id if hasattr(current_user, "property_id") else None

    return {"properties": properties, "count": len(properties), "current_property_id": current_property_id}


# 2. PUT /api/user/switch-property/{property_id} - Switch active property


@sub_router.put("/user/switch-property/{property_id}")
async def switch_property(
    property_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v92 DW: auth-only
):
    """
    Switch user's active property
    Updates user's current property selection
    """
    current_user = await get_current_user(credentials)

    # Verify property exists and belongs to tenant
    property_doc = await db.properties.find_one({"$or": [{"id": property_id, "tenant_id": current_user.tenant_id}, {"property_id": property_id, "tenant_id": current_user.tenant_id}]})

    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found or access denied")

    # Update user's current property
    await db.users.update_one(
        {"id": current_user.id}, {"$set": {"property_id": property_id, "current_property": property_doc.get("name", "Unknown"), "last_property_switch": datetime.now(UTC).isoformat()}}
    )

    # Log the switch
    activity_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "action": "property_switch",
        "property_id": property_id,
        "property_name": property_doc.get("name", "Unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await db.activity_logs.insert_one(activity_log)

    return {"message": "Tesis başarıyla değiştirildi", "property_id": property_id, "property_name": property_doc.get("name", "Unknown"), "switched_at": datetime.now(UTC).isoformat()}
