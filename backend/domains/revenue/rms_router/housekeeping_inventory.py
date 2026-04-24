"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: housekeeping_inventory) ───


@router.get("/housekeeping/inventory")
async def get_inventory(
    category: str | None = None,
    low_stock_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get housekeeping inventory"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if category:
        query['category'] = category

    if low_stock_only:
        query['$expr'] = {'$lte': ['$current_stock', '$minimum_stock']}

    inventory_items = []
    async for item in db.housekeeping_inventory.find(query).sort('name', 1):
        inventory_items.append({
            'id': item.get('id'),
            'name': item.get('name'),
            'category': item.get('category'),  # linen, amenities, cleaning_supplies
            'unit': item.get('unit'),  # pieces, bottles, kg
            'current_stock': item.get('current_stock', 0),
            'minimum_stock': item.get('minimum_stock', 0),
            'maximum_stock': item.get('maximum_stock', 0),
            'unit_cost': item.get('unit_cost', 0),
            'supplier': item.get('supplier', ''),
            'last_restock_date': item.get('last_restock_date').isoformat() if item.get('last_restock_date') else None,
            'is_low_stock': item.get('current_stock', 0) <= item.get('minimum_stock', 0)
        })

    return {
        'inventory_items': inventory_items,
        'total_items': len(inventory_items),
        'low_stock_items': len([i for i in inventory_items if i['is_low_stock']]),
        'categories': list({i['category'] for i in inventory_items})
    }


class InventoryItemCreate(BaseModel):
    name: str
    category: str
    unit: str
    current_stock: int
    minimum_stock: int
    maximum_stock: int
    unit_cost: float
    supplier: str | None = None



@router.post("/housekeeping/inventory/item")
async def create_inventory_item(
    item: InventoryItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("housekeeping")),  # v92 DW
):
    """Create a new inventory item"""
    current_user = await get_current_user(credentials)

    item_id = str(uuid.uuid4())
    inventory_item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'name': item.name,
        'category': item.category,
        'unit': item.unit,
        'current_stock': item.current_stock,
        'minimum_stock': item.minimum_stock,
        'maximum_stock': item.maximum_stock,
        'unit_cost': item.unit_cost,
        'supplier': item.supplier,
        'last_restock_date': datetime.now(UTC),
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.housekeeping_inventory.insert_one(inventory_item)

    return {
        'message': 'Inventory item created',
        'item_id': item_id,
        'name': item.name
    }


class InventoryUsage(BaseModel):
    quantity: int
    used_by: str
    notes: str | None = None



@router.put("/housekeeping/inventory/item/{item_id}/usage")
async def record_inventory_usage(
    item_id: str,
    usage: InventoryUsage,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("housekeeping")),  # v92 DW
):
    """Record inventory usage"""
    current_user = await get_current_user(credentials)

    item = await db.housekeeping_inventory.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    new_stock = item.get('current_stock', 0) - usage.quantity

    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    # Update stock
    await db.housekeeping_inventory.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'current_stock': new_stock}}
    )

    # Log usage
    await db.inventory_usage_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'item_id': item_id,
        'item_name': item.get('name'),
        'quantity': usage.quantity,
        'used_by': usage.used_by,
        'notes': usage.notes,
        'timestamp': datetime.now(UTC)
    })

    return {
        'message': 'Usage recorded',
        'item_id': item_id,
        'new_stock': new_stock,
        'is_low_stock': new_stock <= item.get('minimum_stock', 0)
    }

