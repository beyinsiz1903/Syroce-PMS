"""
pos_inventory

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_module as require_module_rbac  # v89 DW
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover

    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}


# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------


# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel


_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /pos/outlet-sales-breakdown ──
@router.get("/pos/outlet-sales-breakdown")
async def get_outlet_sales_breakdown(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get F&B sales breakdown by outlet"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    if not start_date:
        start_date = (today - timedelta(days=7)).date().isoformat()
    if not end_date:
        end_date = today.date().isoformat()

    # Gerçek POS siparişlerinden outlet kırılımı; sabit/placeholder outlet üretilmez.
    # Veri yoksa boş döner (fail-closed), uydurma kategori yok.
    outlet_sales = {}

    async for order in db.pos_orders.find({"tenant_id": current_user.tenant_id, "created_at": {"$gte": start_date, "$lte": end_date}}):
        outlet = order.get("outlet_name") or "Bilinmeyen"
        if outlet not in outlet_sales:
            outlet_sales[outlet] = {"sales": 0, "orders": 0, "avg_ticket": 0}

        outlet_sales[outlet]["sales"] += order.get("total_amount", 0)
        outlet_sales[outlet]["orders"] += 1

    # Calculate averages
    for outlet in outlet_sales:
        if outlet_sales[outlet]["orders"] > 0:
            outlet_sales[outlet]["avg_ticket"] = round(outlet_sales[outlet]["sales"] / outlet_sales[outlet]["orders"], 2)
        outlet_sales[outlet]["sales"] = round(outlet_sales[outlet]["sales"], 2)

    total_sales = sum(o["sales"] for o in outlet_sales.values())

    return {
        "outlets": outlet_sales,
        "total_sales": round(total_sales, 2),
        "period": {"start": start_date, "end": end_date},
        "data_available": len(outlet_sales) > 0,
    }


# ── GET /pos/inventory-movements ──
@router.get("/pos/inventory-movements")
async def get_inventory_movements(
    item_id: str | None = None, movement_type: str | None = None, date_from: str | None = None, limit: int = 50, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get inventory movements (stock in/out)"""
    current_user = await get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id}

    if item_id:
        query["item_id"] = item_id
    if movement_type:
        query["movement_type"] = movement_type
    if date_from:
        query["created_at"] = {"$gte": date_from}

    movements = []
    async for movement in db.inventory_movements.find(query).sort("created_at", -1).limit(limit):
        movement.pop("_id", None)
        movements.append(movement)

    # Boşsa sahte hareket üretilmez; gerçek veri yoksa boş döner (fail-closed).
    return {"movements": movements, "count": len(movements)}


# ── POST /pos/inventory-movement ──
@router.post("/pos/inventory-movement")
async def create_inventory_movement(
    movement_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("pos")),  # v89 DW
):
    """Create a new inventory movement"""
    current_user = await get_current_user(credentials)

    movement = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "item_id": movement_data.get("item_id"),
        "item_name": movement_data.get("item_name"),
        "movement_type": movement_data.get("movement_type"),  # 'in' or 'out'
        "quantity": movement_data.get("quantity"),
        "unit": movement_data.get("unit"),
        "reference": movement_data.get("reference"),
        "notes": movement_data.get("notes", ""),
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db.inventory_movements.insert_one(movement)

    # Update item stock (tenant-scoped: cross-tenant stok yazımını engeller)
    if movement["movement_type"] == "in":
        await db.inventory_items.update_one({"id": movement["item_id"], "tenant_id": current_user.tenant_id}, {"$inc": {"stock": movement["quantity"]}})
    else:
        await db.inventory_items.update_one({"id": movement["item_id"], "tenant_id": current_user.tenant_id}, {"$inc": {"stock": -movement["quantity"]}})

    return {"message": "Movement recorded", "movement_id": movement["id"]}


# ── GET /pos/shift-metrics ──
@router.get("/pos/shift-metrics")
async def get_shift_metrics(date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get POS sales metrics by shift (morning/afternoon/evening)"""
    current_user = await get_current_user(credentials)

    if not date:
        date = datetime.now(UTC).date().isoformat()

    shift_data = {
        "morning": {"sales": 0, "orders": 0, "hours": "06:00-14:00"},
        "afternoon": {"sales": 0, "orders": 0, "hours": "14:00-18:00"},
        "evening": {"sales": 0, "orders": 0, "hours": "18:00-23:00"},
    }

    # Gercek POS siparislerini vardiya saatlerine gore topla (created_at saatine gore)
    async for order in db.pos_orders.find({"tenant_id": current_user.tenant_id, "order_date": date}):
        created_at = order.get("created_at", "")
        if isinstance(created_at, str):
            hour = int(created_at.split("T")[1].split(":")[0]) if "T" in created_at else 12
        else:
            hour = created_at.hour if hasattr(created_at, "hour") else 12

        if 6 <= hour < 14:
            shift = "morning"
        elif 14 <= hour < 18:
            shift = "afternoon"
        else:
            shift = "evening"

        shift_data[shift]["sales"] += order.get("total_amount", 0)
        shift_data[shift]["orders"] += 1

    # Round values
    for shift in shift_data:
        shift_data[shift]["sales"] = round(shift_data[shift]["sales"], 2)

    return {"shifts": shift_data, "date": date}
