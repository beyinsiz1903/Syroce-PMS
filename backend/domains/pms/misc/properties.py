"""Auto-split from misc_router.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from models.schemas import CreatePropertyRequest, User
from modules.pms_core.chain_access import resolve_chain_properties, tenant_id_from_document
from modules.pms_core.role_permission_service import require_op
from routers.properties_admin import PropertyCreate
from routers.properties_admin import create_property as create_chain_property

logger = logging.getLogger(__name__)

sub_router = APIRouter()


@sub_router.post("/multi-property/properties")
async def create_property(
    request: CreatePropertyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Compatibility entry point for creating a real chain tenant.

    Older builds wrote an unrelated document to ``db.properties``.  That did
    not provision a tenant, rooms, modules, or an authenticated property
    boundary, so it created a misleading second property model.  Keep the URL
    for older clients but route it through the authoritative tenant flow.
    """
    if request.status != "active":
        raise HTTPException(
            status_code=422,
            detail="Yeni tesis aktif olarak oluşturulur; durum değişikliği tesis yönetiminden yapılır",
        )
    result = await create_chain_property(
        PropertyCreate(
            property_name=request.property_name,
            property_type=request.property_type,
            location=request.location,
            total_rooms=request.total_rooms,
        ),
        current_user,
    )
    return {**result, "property_code": request.property_code}


@sub_router.get("/multi-property/consolidated-report")
async def get_consolidated_report(start_date: str, end_date: str, metric: str = "occupancy", current_user: User = Depends(get_current_user)):
    """Get a consolidated report for the caller's active chain only."""
    _, properties = await resolve_chain_properties(current_user, require_headquarters=True)

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1

    report_data = []

    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()

        day_data = {"date": current_date, "properties": []}

        for prop in properties:
            # Simplified metrics
            property_id = tenant_id_from_document(prop)
            if metric == "occupancy":
                rooms = await db.rooms.count_documents({"tenant_id": property_id})
                occupied = await db.rooms.count_documents({"tenant_id": property_id, "room_status": "occupied"})
                value = (occupied / rooms * 100) if rooms > 0 else 0
            elif metric == "revenue":
                pipeline = [{"$match": {"tenant_id": property_id, "charge_date": current_date, "voided": False}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]
                result = await db.folio_charges.aggregate(pipeline).to_list(1)
                value = result[0]["total"] if result else 0.0
            else:
                value = 0

            day_data["properties"].append(
                {
                    "property_id": property_id,
                    "property_name": prop.get("property_name") or prop.get("hotel_name") or property_id,
                    "value": round(value, 2),
                }
            )

        report_data.append(day_data)

    return {"start_date": start_date, "end_date": end_date, "metric": metric, "data": report_data}


@sub_router.get("/properties/quick-list")
async def get_quick_property_list(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get quick property list for fast switching
    Returns only essential information for performance
    """
    current_user = await get_current_user(credentials)

    # A JWT is scoped to one tenant.  Listing a sibling here made the old UI
    # look as if switching would change tenant context even though it could not.
    # Central users use the dedicated multi-property dashboard instead.
    from core.tenant_db import get_system_db

    tenant = await get_system_db().tenants.find_one(
        {"$or": [{"id": current_user.tenant_id}, {"tenant_id": current_user.tenant_id}]},
        {"_id": 0},
    )
    properties = []
    if tenant:
        tenant_id = tenant_id_from_document(tenant)
        properties.append(
            {
                "id": tenant_id,
                "property_id": tenant_id,
                "name": tenant.get("property_name") or tenant.get("hotel_name") or tenant_id,
                "location": tenant.get("location") or "",
                "type": tenant.get("property_type") or "hotel",
                "logo": "",
                "is_active": tenant.get("subscription_status", "active") == "active",
                "room_count": int(tenant.get("total_rooms") or 0),
                "is_current_tenant": True,
            }
        )

    # Get user's current property
    current_property_id = current_user.tenant_id

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

    if property_id != current_user.tenant_id:
        raise HTTPException(
            status_code=409,
            detail="Tesis değişimi oturum belirtecini değiştirmez; zincir görünümü için Çoklu Tesis ekranını kullanın",
        )

    # Log the switch
    activity_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "action": "property_switch",
        "property_id": property_id,
        "property_name": "Mevcut tesis",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await db.activity_logs.insert_one(activity_log)

    return {"message": "Mevcut tesis zaten seçili", "property_id": property_id, "property_name": "Mevcut tesis", "switched_at": datetime.now(UTC).isoformat()}
