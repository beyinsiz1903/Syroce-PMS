"""
pos

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Mobile

Extracted from legacy_routes.py — Mobile dashboard, GM mobile, department mobile endpoints.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    require_op,
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW



# ============================================================================
# MOBILE ENDPOINTS - Department-Based Mobile Dashboard APIs
# ============================================================================

# Mobile Endpoint Pydantic Models
class ProcessNoShowRequest(BaseModel):
    booking_id: str

class ChangeRoomRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str | None = None

class QuickTaskRequest(BaseModel):
    room_id: str
    task_type: str
    priority: str = 'normal'
    assigned_to: str | None = None
    notes: str | None = None

class QuickIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = 'normal'

class QuickOrderItem(BaseModel):
    item_id: str
    quantity: int = 1

class QuickOrderRequest(BaseModel):
    outlet_id: str
    table_number: str | None = None
    items: list[QuickOrderItem] = []
    notes: str | None = None

class MenuPriceUpdateRequest(BaseModel):
    new_price: float
    reason: str | None = None

# --------------------------------------------------------------------------
# GM Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Front Desk Mobile Dashboard Endpoints
# --------------------------------------------------------------------------











# --------------------------------------------------------------------------
# Housekeeping Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Housekeeping Enhanced - Inspection, Lost & Found, Task Assignment, Timer
# --------------------------------------------------------------------------

























# --------------------------------------------------------------------------
# Maintenance Mobile Dashboard Endpoints
# --------------------------------------------------------------------------





# --------------------------------------------------------------------------
# Technical Service Enhancements - SLA, Spare Parts, Task Management
# --------------------------------------------------------------------------























# --------------------------------------------------------------------------
# F&B Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Finance Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["mobile"])


# ── POST /pos/mobile/quick-order ──
@router.post("/pos/mobile/quick-order")
async def create_quick_order_mobile(
    request: QuickOrderRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("pos")),  # v89 DW
):
    """Create a quick POS order from mobile"""
    current_user = await get_current_user(credentials)
    outlet_id = request.outlet_id
    table_number = request.table_number
    items = [item.dict() for item in request.items]
    notes = request.notes

    # Validate outlet
    outlet = await db.pos_outlets.find_one({
        'id': outlet_id,
        'tenant_id': current_user.tenant_id
    })

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Calculate total
    subtotal = 0.0
    order_items = []

    for item in items:
        menu_item = await db.pos_menu_items.find_one({
            'id': item.get('item_id'),
            'tenant_id': current_user.tenant_id
        })

        if not menu_item:
            continue

        quantity = item.get('quantity', 1)
        item_price = menu_item.get('price', 0)
        item_total = item_price * quantity
        subtotal += item_total

        order_items.append({
            'item_id': item.get('item_id'),
            'item_name': menu_item.get('name'),
            'quantity': quantity,
            'unit_price': item_price,
            'total': item_total
        })

    # Calculate tax (18% VAT)
    tax = subtotal * 0.18
    total = subtotal + tax

    # Create order
    order_id = str(uuid.uuid4())
    order = {
        'id': order_id,
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id,
        'outlet_name': outlet.get('name'),
        'table_number': table_number,
        'items': order_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'status': 'pending',
        'notes': notes,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.pos_orders.insert_one(order)

    return {
        'message': 'Order created successfully',
        'order_id': order_id,
        'outlet_name': outlet.get('name'),
        'table_number': table_number,
        'total': total,
        'items_count': len(order_items)
    }
# ── PUT /pos/mobile/menu-items/{item_id}/price ──
@router.put("/pos/mobile/menu-items/{item_id}/price")
async def update_menu_item_price_mobile(
    item_id: str,
    request: MenuPriceUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("pos")),  # v89 DW
):
    """Update menu item price from mobile"""
    current_user = await get_current_user(credentials)
    new_price = request.new_price
    reason = request.reason

    # Find menu item
    menu_item = await db.pos_menu_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    old_price = menu_item.get('price')

    # Update price
    await db.pos_menu_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'price': new_price,
                'price_updated_at': datetime.now(UTC),
                'price_updated_by': current_user.username
            }
        }
    )

    # Log price change
    await db.audit_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.user_id,
        'user_name': current_user.username,
        'action': 'MENU_PRICE_UPDATE',
        'entity_type': 'menu_item',
        'entity_id': item_id,
        'changes': {
            'item_name': menu_item.get('name'),
            'old_price': old_price,
            'new_price': new_price,
            'reason': reason
        },
        'timestamp': datetime.now(UTC)
    })

    return {
        'message': 'Menu item price updated',
        'item_id': item_id,
        'item_name': menu_item.get('name'),
        'old_price': old_price,
        'new_price': new_price
    }
