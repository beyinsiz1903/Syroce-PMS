"""
PMS / POS & F&B Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.helpers import (
    require_feature,
)
from core.security import (
    _is_super_admin,
    get_current_user,
    security,
)
from models.enums import ChargeCategory
from models.schemas import CreatePOSTransactionRequest, FolioCharge, Order, OrderCreate, User
from modules.pms_core.role_permission_service import require_module, require_op  # v89 DW
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW

try:
    from websocket_server import broadcast_kitchen_orders
except Exception:  # pragma: no cover
    async def broadcast_kitchen_orders(tenant_id: str, orders: Any):
        return None


async def _get_active_kitchen_orders(tenant_id: str, statuses: list[str] | None = None):
    query = {'tenant_id': tenant_id}
    if statuses:
        query['status'] = {'$in': statuses}
    else:
        query['status'] = {'$in': ['pending', 'preparing']}
    return await db.kitchen_orders.find(query, {'_id': 0}).sort(
        [('priority', -1), ('ordered_at', 1)]
    ).to_list(200)


async def _next_kitchen_order_number(tenant_id: str) -> int:
    last_order = await db.kitchen_orders.find({'tenant_id': tenant_id}).sort('order_number', -1).limit(1).to_list(1)
    return (last_order[0]['order_number'] + 1) if last_order else 1


async def _broadcast_kitchen_queue(tenant_id: str) -> None:
    try:
        orders = await _get_active_kitchen_orders(tenant_id)
        await broadcast_kitchen_orders(tenant_id, orders)
    except Exception as exc:
        logging.warning(f"Kitchen broadcast failed: {exc}")


def calculate_table_duration(opened_at: Any) -> int:
    """Return open-table duration in minutes; 0 on bad input."""
    if not opened_at:
        return 0
    try:
        if isinstance(opened_at, str):
            dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
        else:
            dt = opened_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int((datetime.now(UTC) - dt).total_seconds() // 60)
    except Exception:
        return 0


def create_default_table_layout() -> list[dict[str, Any]]:
    """Return a generic 8-table layout for first-time setup."""
    return [
        {'id': str(uuid.uuid4()), 'number': str(i + 1), 'capacity': 4, 'status': 'available', 'zone': 'main'}
        for i in range(8)
    ]


async def recalculate_folio_balance(folio_id: str, tenant_id: str) -> float:
    """Recompute folio balance after F&B post; lazy-imports core helper."""
    try:
        from core.utils import calculate_folio_balance
        return await calculate_folio_balance(folio_id, tenant_id)
    except Exception:
        return 0.0


def get_menu_recommendation(_guest_profile: dict | None = None) -> list[str]:
    """Heuristic menu recommendation stub — to be replaced by ML model."""
    return ['Chef\'s Special', 'Local Wine Pairing', 'Seasonal Dessert']

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / POS & F&B"])


# ── Inline Models ──

from enum import Enum


class POSCategory(str, Enum):
    FOOD = "food"
    BEVERAGE = "beverage"
    ALCOHOL = "alcohol"
    DESSERT = "dessert"
    APPETIZER = "appetizer"


class POSMenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_name: str
    category: POSCategory
    unit_price: float
    available: bool = True


class POSOrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    item_name: str
    category: POSCategory
    quantity: int
    unit_price: float
    total_price: float


class POSOrderItemRequest(BaseModel):
    item_id: str
    quantity: int = 1


class POSOrderCreateRequest(BaseModel):
    booking_id: str | None = None
    folio_id: str | None = None
    order_items: list[POSOrderItemRequest]


class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str | None = None
    guest_id: str | None = None
    folio_id: str | None = None
    order_items: list[POSOrderItem]
    subtotal: float
    tax_amount: float
    total_amount: float
    status: str = "pending"  # pending, completed, cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment_type: str  # in, out, adjustment
    quantity: int
    reason: str
    notes: str | None = None


class UpdateOrderStatusRequest(BaseModel):
    status: str  # pending, preparing, ready, served
    notes: str | None = None


class TableLayout(BaseModel):
    """Table layout for restaurant floor plan"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    outlet_id: str
    table_number: str
    seats: int
    position_x: float  # X coordinate on floor plan
    position_y: float  # Y coordinate on floor plan
    shape: str = "rectangle"  # rectangle, circle, square
    width: float = 100
    height: float = 100
    status: str = "available"  # available, occupied, reserved, dirty
    current_transaction_id: str | None = None
    server_assigned: str | None = None


class KitchenOrderItem(BaseModel):
    """Kitchen order item for KDS"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_id: str
    table_number: str
    item_name: str
    quantity: int
    special_instructions: str | None = None
    station: str  # hot_kitchen, cold_kitchen, bar, pastry
    status: str = "pending"  # pending, preparing, ready, served
    priority: str = "normal"  # urgent, high, normal
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ready_at: datetime | None = None
    served_at: datetime | None = None


class Alert(BaseModel):
    """Universal alert model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    alert_type: str  # housekeeping, maintenance, ota, overbooking, rms, ar, marketplace, review
    priority: str  # low, normal, high, urgent
    title: str
    description: str
    source_module: str
    source_id: str | None = None
    assigned_to: str | None = None
    status: str = "unread"  # unread, read, acknowledged, resolved
    action_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None


@router.get("/fnb/kitchen-display")
async def get_kitchen_orders(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    statuses = status.split(',') if status else None
    orders = await _get_active_kitchen_orders(current_user.tenant_id, statuses=statuses)
    return {'orders': orders, 'total': len(orders)}


@router.post("/fnb/kitchen-order")
async def create_kitchen_order(
    order_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    if not order_data.get('items'):
        raise HTTPException(status_code=400, detail="Order items required")

    order = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'order_number': await _next_kitchen_order_number(current_user.tenant_id),
        'table_number': order_data.get('table_number'),
        'room_number': order_data.get('room_number'),
        'priority': order_data.get('priority', 'normal'),
        'status': 'pending',
        'station': order_data.get('station'),
        'items': order_data.get('items'),
        'notes': order_data.get('notes'),
        'ordered_by': current_user.name,
        'ordered_at': datetime.now(UTC).isoformat(),
    }
    await db.kitchen_orders.insert_one(order)
    await _broadcast_kitchen_queue(current_user.tenant_id)
    order.pop('_id', None)
    return {'success': True, 'order': order}


@router.put("/fnb/kitchen-order/{order_id}/status")
async def update_kitchen_order_status_v2(
    order_id: str,
    status: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    update_data = {'status': status}
    if status == 'preparing':
        update_data['started_at'] = datetime.now(UTC).isoformat()
    if status in ['ready', 'served']:
        update_data['ready_at'] = datetime.now(UTC).isoformat()
    result = await db.kitchen_orders.update_one(
        {'tenant_id': current_user.tenant_id, 'id': order_id},
        {'$set': update_data},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    await _broadcast_kitchen_queue(current_user.tenant_id)
    return {'success': True, 'order_id': order_id, 'status': status}


@router.post("/fnb/kitchen-order/{order_id}/complete")
async def complete_kitchen_order(order_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    await db.kitchen_orders.update_one(
        {'id': order_id},
        {'$set': {'status': 'ready', 'ready_at': datetime.now(UTC).isoformat()}}
    )
    await _broadcast_kitchen_queue(current_user.tenant_id)
    return {'success': True, 'message': 'Sipariş hazır olarak işaretlendi'}

# ============= PHOTO UPLOAD (KAT HİZMETLERİ İÇİN) =============



@router.post("/marketplace/orders", response_model=Order, dependencies=[Depends(require_feature("hidden_marketplace"))])
async def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    order = Order(tenant_id=current_user.tenant_id, **order_data.model_dump())
    order_dict = order.model_dump()
    order_dict['created_at'] = order_dict['created_at'].isoformat()
    await db.orders.insert_one(order_dict)
    return order



# rbac-allow: cache-rbac — POS F&B orders operasyonel
@router.get("/marketplace/orders", response_model=list[Order], dependencies=[Depends(require_feature("hidden_marketplace"))])
@cached(ttl=300, key_prefix="marketplace_orders")  # Cache for 5 min
async def get_orders(current_user: User = Depends(get_current_user)):
    orders = await db.orders.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return orders

# ============= HOTEL INVENTORY MANAGEMENT =============



@router.post("/pos/transaction")
async def create_pos_transaction(
    request: CreatePOSTransactionRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Create POS transaction"""
    transaction = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'transaction_date': datetime.now(UTC).date().isoformat(),
        'transaction_time': datetime.now(UTC).time().isoformat(),
        'amount': request.amount,
        'payment_method': request.payment_method,
        'folio_id': request.folio_id,
        'status': 'completed',
        'processed_by': current_user.id,
        'created_at': datetime.now(UTC).isoformat()
    }

    transaction_copy = transaction.copy()
    await db.pos_transactions.insert_one(transaction_copy)
    return transaction



@router.post("/pos/check-split")
async def split_check(
    transaction_id: str,
    split_type: str,  # equal, by_item, custom
    split_count: int | None = 2,
    split_details: dict | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """
    Split restaurant check
    - Equal split (N ways)
    - By item
    - Custom amounts
    """
    transaction = await db.pos_transactions.find_one({
        'id': transaction_id,
        'tenant_id': current_user.tenant_id
    })

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    total_amount = transaction.get('total_amount', 0)
    # Item field is stored as 'order_items' on POS orders; older transactions used 'items'.
    items = transaction.get('order_items') or transaction.get('items', [])

    split_transactions = []

    if split_type == 'equal':
        # Equal split
        amount_per_split = total_amount / split_count
        for i in range(split_count):
            split_transactions.append({
                'split_number': i + 1,
                'amount': round(amount_per_split, 2),
                'items': 'All items (split equally)'
            })

    elif split_type == 'by_item':
        # By item (from split_details)
        if not split_details:
            raise HTTPException(status_code=400, detail="split_details required for by_item split")

        for split_num, item_indices in split_details.items():
            split_amount = sum(items[i].get('price', 0) for i in item_indices if i < len(items))
            split_items = [items[i].get('name') for i in item_indices if i < len(items)]
            split_transactions.append({
                'split_number': int(split_num),
                'amount': round(split_amount, 2),
                'items': split_items
            })

    elif split_type == 'custom':
        # Custom amounts
        if not split_details:
            raise HTTPException(status_code=400, detail="split_details required for custom split")

        for split_num, amount in split_details.items():
            split_transactions.append({
                'split_number': int(split_num),
                'amount': round(amount, 2),
                'items': 'Custom split'
            })

    # Update original transaction
    await db.pos_transactions.update_one(
        {'id': transaction_id},
        {'$set': {
            'status': 'split',
            'split_type': split_type,
            'split_count': len(split_transactions)
        }}
    )

    return {
        'success': True,
        'original_transaction_id': transaction_id,
        'original_amount': round(total_amount, 2),
        'split_type': split_type,
        'split_count': len(split_transactions),
        'splits': split_transactions
    }




@router.post("/pos/transfer-table")
async def transfer_table(
    from_table: str,
    to_table: str,
    outlet_id: str,
    transfer_all: bool = True,
    items_to_transfer: list[int] | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Transfer items from one table to another"""
    # Get active transaction from source table
    source_transaction = await db.pos_transactions.find_one({
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id,
        'table_number': from_table,
        'status': 'open'
    })

    if not source_transaction:
        raise HTTPException(status_code=404, detail=f"No active transaction found for table {from_table}")

    if transfer_all:
        # Transfer entire table
        await db.pos_transactions.update_one(
            {'id': source_transaction.get('id')},
            {'$set': {'table_number': to_table}}
        )

        return {
            'success': True,
            'message': f'Table {from_table} transferred to {to_table}',
            'transaction_id': source_transaction.get('id'),
            'items_transferred': len(source_transaction.get('items', []))
        }

    else:
        # Transfer specific items (not implemented in MVP)
        raise HTTPException(status_code=501, detail="Partial transfer not yet implemented")




@router.post("/pos/happy-hour")
async def apply_happy_hour_discount(
    outlet_id: str,
    discount_pct: float,
    start_time: str,  # HH:MM
    end_time: str,
    applicable_categories: list[str] = [],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """
    Apply happy hour discount
    - Time-based automatic discount
    - Category-specific (e.g., only beverages)
    """
    happy_hour = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id,
        'discount_pct': discount_pct,
        'start_time': start_time,
        'end_time': end_time,
        'applicable_categories': applicable_categories,
        'active': True,
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.happy_hour_rules.insert_one(happy_hour)

    return {
        'success': True,
        'happy_hour_id': happy_hour['id'],
        'message': f'Happy hour created: {discount_pct}% off {start_time}-{end_time}'
    }


# ============= CHANNEL MANAGER ENHANCEMENTS =============



@router.get("/pos/table-layout/{outlet_id}")
async def get_table_layout(
    outlet_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get restaurant floor plan with table layout
    - Visual table arrangement
    - Table status (available, occupied, reserved, dirty)
    - Current transactions
    """
    tables = []
    raw_tables = await db.table_layouts.find({
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id
    }).to_list(length=None)
    # Batch-fetch all open transactions referenced by tables
    txn_ids = [t.get('current_transaction_id') for t in raw_tables if t.get('current_transaction_id')]
    txns_by_id: dict = {}
    if txn_ids:
        async for tx in db.pos_transactions.find(
            {'id': {'$in': txn_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'total_amount': 1, 'guests': 1},
        ):
            txns_by_id[tx['id']] = tx
    for table in raw_tables:
        transaction = txns_by_id.get(table.get('current_transaction_id'))

        tables.append({
            'id': table.get('id'),
            'table_number': table.get('table_number'),
            'seats': table.get('seats'),
            'position': {
                'x': table.get('position_x'),
                'y': table.get('position_y')
            },
            'shape': table.get('shape'),
            'width': table.get('width'),
            'height': table.get('height'),
            'status': table.get('status'),
            'server_assigned': table.get('server_assigned'),
            'current_bill': round(transaction.get('total_amount', 0), 2) if transaction else 0,
            'guest_count': transaction.get('guests', 0) if transaction else 0,
            'duration_minutes': calculate_table_duration(table) if table.get('status') == 'occupied' else 0
        })

    # If no tables exist, only auto-create when outlet is real (avoid 500 for unknown ids)
    if not tables:
        outlet = await db.pos_outlets.find_one({
            'id': outlet_id,
            'tenant_id': current_user.tenant_id,
        })
        if not outlet:
            raise HTTPException(status_code=404, detail="Outlet bulunamadi")
        default_tables = create_default_table_layout(current_user.tenant_id, outlet_id)
        for table_data in default_tables:
            await db.table_layouts.insert_one(table_data)
            tables.append({
                'id': table_data['id'],
                'table_number': table_data['table_number'],
                'seats': table_data['seats'],
                'position': {'x': table_data['position_x'], 'y': table_data['position_y']},
                'shape': table_data['shape'],
                'width': table_data['width'],
                'height': table_data['height'],
                'status': 'available',
                'server_assigned': None,
                'current_bill': 0,
                'guest_count': 0,
                'duration_minutes': 0
            })

    return {
        'outlet_id': outlet_id,
        'total_tables': len(tables),
        'available': sum(1 for t in tables if t['status'] == 'available'),
        'occupied': sum(1 for t in tables if t['status'] == 'occupied'),
        'reserved': sum(1 for t in tables if t['status'] == 'reserved'),
        'tables': tables
    }




@router.post("/pos/table-layout/update")
async def update_table_layout(
    table_id: str,
    position_x: float | None = None,
    position_y: float | None = None,
    seats: int | None = None,
    server_assigned: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """Update table layout - drag & drop positioning"""
    updates = {}
    if position_x is not None:
        updates['position_x'] = position_x
    if position_y is not None:
        updates['position_y'] = position_y
    if seats is not None:
        updates['seats'] = seats
    if server_assigned is not None:
        updates['server_assigned'] = server_assigned

    await db.table_layouts.update_one(
        {'id': table_id, 'tenant_id': current_user.tenant_id},
        {'$set': updates}
    )

    return {'success': True, 'message': 'Table layout updated'}




@router.get("/pos/split-bill-ui/{transaction_id}")
async def get_split_bill_ui_data(
    transaction_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get transaction data formatted for split bill UI
    - Line items with selection
    - Multiple payment methods
    - Split strategies
    """
    transaction = await db.pos_transactions.find_one({
        'id': transaction_id,
        'tenant_id': current_user.tenant_id
    })

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    items = transaction.get('items', [])

    # Format items for split UI
    formatted_items = []
    for idx, item in enumerate(items):
        formatted_items.append({
            'index': idx,
            'name': item.get('name'),
            'quantity': item.get('quantity', 1),
            'unit_price': item.get('price', 0),
            'total': item.get('price', 0) * item.get('quantity', 1),
            'selected_for_split': False,
            'split_assignee': None  # Which guest (1, 2, 3, etc.)
        })

    return {
        'transaction_id': transaction_id,
        'table_number': transaction.get('table_number'),
        'total_amount': transaction.get('total_amount', 0),
        'items': formatted_items,
        'split_strategies': [
            {'id': 'equal', 'name': 'Equal Split', 'description': 'Split bill equally among N people'},
            {'id': 'by_item', 'name': 'By Item', 'description': 'Assign items to specific people'},
            {'id': 'percentage', 'name': 'By Percentage', 'description': 'Split by custom percentages'},
            {'id': 'custom', 'name': 'Custom Amount', 'description': 'Enter custom amounts for each person'}
        ],
        'payment_methods': ['cash', 'card', 'mobile', 'room_charge']
    }




@router.post("/pos/kds/update-order-status")
async def update_kitchen_order_status(
    order_id: str,
    new_status: str,  # preparing, ready, served
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Update kitchen order status from KDS"""
    updates = {'status': new_status}

    if new_status == 'ready':
        updates['ready_at'] = datetime.now(UTC).isoformat()
    elif new_status == 'served':
        updates['served_at'] = datetime.now(UTC).isoformat()

    await db.kitchen_orders.update_one(
        {'id': order_id, 'tenant_id': current_user.tenant_id},
        {'$set': updates}
    )

    return {'success': True, 'order_id': order_id, 'new_status': new_status}




@router.post("/pos/room-charge-restrictions")
async def set_room_charge_restrictions(
    max_daily_charge: float | None = None,
    require_supervisor_approval: bool = False,
    allowed_categories: list[str] | None = None,
    restricted_hours: dict[str, str] | None = None,  # {"start": "02:00", "end": "06:00"}
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """
    Room charge restrictions
    - Max daily charge limit
    - Supervisor approval required
    - Category restrictions (e.g., no alcohol)
    - Time restrictions (e.g., no charges 2am-6am)
    """
    restrictions = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'max_daily_charge': max_daily_charge,
        'require_supervisor_approval': require_supervisor_approval,
        'allowed_categories': allowed_categories or ['food', 'beverage', 'minibar'],
        'restricted_hours': restricted_hours,
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.name
    }

    # Store or update restrictions
    existing = await db.pos_room_charge_restrictions.find_one({
        'tenant_id': current_user.tenant_id
    })

    if existing:
        await db.pos_room_charge_restrictions.update_one(
            {'tenant_id': current_user.tenant_id},
            {'$set': restrictions}
        )
    else:
        await db.pos_room_charge_restrictions.insert_one(restrictions)

    return {
        'success': True,
        'message': 'Room charge restrictions updated',
        'restrictions': restrictions
    }




@router.post("/pos/validate-room-charge")
async def validate_room_charge(
    booking_id: str,
    amount: float,
    category: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """
    Validate if room charge is allowed
    - Check against restrictions
    - Return validation result
    """
    # Get restrictions
    restrictions = await db.pos_room_charge_restrictions.find_one({
        'tenant_id': current_user.tenant_id
    })

    validation_result = {
        'allowed': True,
        'reason': None,
        'requires_approval': False
    }

    if restrictions:
        # Check max daily charge
        if restrictions.get('max_daily_charge'):
            # Get today's charges
            today = datetime.now().date().isoformat()
            daily_total = 0
            async for charge in db.folio_charges.find({
                'booking_id': booking_id,
                'date': {'$gte': today}
            }):
                daily_total += charge.get('total', 0)

            if daily_total + amount > restrictions['max_daily_charge']:
                validation_result['allowed'] = False
                validation_result['reason'] = f"Exceeds daily limit of ${restrictions['max_daily_charge']}"
                return validation_result

        # Check allowed categories
        if restrictions.get('allowed_categories'):
            if category not in restrictions['allowed_categories']:
                validation_result['allowed'] = False
                validation_result['reason'] = f"Category '{category}' not allowed for room charge"
                return validation_result

        # Check restricted hours
        if restrictions.get('restricted_hours'):
            current_time = datetime.now().time()
            start_time = datetime.strptime(restrictions['restricted_hours']['start'], '%H:%M').time()
            end_time = datetime.strptime(restrictions['restricted_hours']['end'], '%H:%M').time()

            if start_time <= current_time <= end_time:
                validation_result['allowed'] = False
                validation_result['reason'] = f"Room charges restricted between {restrictions['restricted_hours']['start']}-{restrictions['restricted_hours']['end']}"
                return validation_result

        # Check if approval required
        if restrictions.get('require_supervisor_approval'):
            validation_result['requires_approval'] = True

    return validation_result


# ============= HOTEL INTERNAL MESSAGING =============



@router.get("/fnb/dashboard")
async def get_fnb_dashboard(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get F&B dashboard overview"""
    current_user = await get_current_user(credentials)

    # Default to today
    if not date:
        date = datetime.now(UTC).strftime('%Y-%m-%d')

    target_date = datetime.fromisoformat(date)
    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    # Get F&B charges
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'charge_category': {'$in': ['food', 'beverage']},
        'date': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    food_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'food')
    beverage_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'beverage')
    total_revenue = food_revenue + beverage_revenue

    # Get POS orders
    orders = await db.pos_orders.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    orders_count = len(orders)
    avg_order_value = round(total_revenue / orders_count, 2) if orders_count > 0 else 0

    # Get table turnover (simplified)
    tables_used = len({o.get('table_number') for o in orders if o.get('table_number')})

    # Previous day comparison
    prev_start = start - timedelta(days=1)
    prev_end = start

    prev_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'charge_category': {'$in': ['food', 'beverage']},
        'date': {
            '$gte': prev_start.isoformat(),
            '$lte': prev_end.isoformat()
        }
    }).to_list(10000)

    prev_revenue = sum(c.get('total', 0) for c in prev_charges)
    revenue_change = round(((total_revenue - prev_revenue) / prev_revenue * 100), 2) if prev_revenue > 0 else 0

    return {
        'date': date,
        'summary': {
            'total_revenue': round(total_revenue, 2),
            'food_revenue': round(food_revenue, 2),
            'beverage_revenue': round(beverage_revenue, 2),
            'orders_count': orders_count,
            'avg_order_value': avg_order_value,
            'tables_used': tables_used,
            'revenue_change': revenue_change
        }
    }



@router.get("/fnb/sales-report")
async def get_fnb_sales_report(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get F&B sales report"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get charges
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'charge_category': {'$in': ['food', 'beverage']},
        'date': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Daily breakdown
    daily_sales = {}
    for charge in charges:
        date_str = charge.get('date', '')[:10]
        if date_str not in daily_sales:
            daily_sales[date_str] = {'food': 0, 'beverage': 0}

        category = charge.get('charge_category')
        daily_sales[date_str][category] += charge.get('total', 0)

    daily_data = []
    for date_str in sorted(daily_sales.keys()):
        daily_data.append({
            'date': date_str,
            'food': round(daily_sales[date_str]['food'], 2),
            'beverage': round(daily_sales[date_str]['beverage'], 2),
            'total': round(daily_sales[date_str]['food'] + daily_sales[date_str]['beverage'], 2)
        })

    # Category totals
    total_food = sum(d['food'] for d in daily_data)
    total_beverage = sum(d['beverage'] for d in daily_data)
    total_sales = total_food + total_beverage

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'summary': {
            'total_sales': round(total_sales, 2),
            'food_sales': round(total_food, 2),
            'beverage_sales': round(total_beverage, 2),
            'food_percentage': round((total_food / total_sales * 100), 2) if total_sales > 0 else 0,
            'beverage_percentage': round((total_beverage / total_sales * 100), 2) if total_sales > 0 else 0
        },
        'daily_sales': daily_data
    }



@router.get("/fnb/menu-performance")
async def get_fnb_menu_performance(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get menu item performance analysis"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get POS orders with item details
    orders = await db.pos_orders.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Aggregate by menu item
    menu_stats = {}
    for order in orders:
        items = order.get('items', [])
        for item in items:
            item_name = item.get('item_name', 'Unknown')
            quantity = item.get('quantity', 1)
            price = item.get('price', 0)

            if item_name not in menu_stats:
                menu_stats[item_name] = {
                    'quantity_sold': 0,
                    'revenue': 0,
                    'orders_count': 0
                }

            menu_stats[item_name]['quantity_sold'] += quantity
            menu_stats[item_name]['revenue'] += price * quantity
            menu_stats[item_name]['orders_count'] += 1

    # Format and sort
    menu_items = []
    for item_name, stats in menu_stats.items():
        menu_items.append({
            'item_name': item_name,
            'quantity_sold': stats['quantity_sold'],
            'revenue': round(stats['revenue'], 2),
            'orders_count': stats['orders_count'],
            'avg_price': round(stats['revenue'] / stats['quantity_sold'], 2) if stats['quantity_sold'] > 0 else 0
        })

    # Sort by revenue
    menu_items.sort(key=lambda x: x['revenue'], reverse=True)

    # Get top 10 and bottom 5
    top_items = menu_items[:10]
    bottom_items = menu_items[-5:] if len(menu_items) > 5 else []

    total_revenue = sum(item['revenue'] for item in menu_items)

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'total_items': len(menu_items),
        'total_revenue': round(total_revenue, 2),
        'top_performers': top_items,
        'bottom_performers': bottom_items
    }



@router.get("/fnb/revenue-chart")
async def get_fnb_revenue_chart(
    period: str = "30days",  # 7days, 30days, 90days
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get F&B revenue chart data"""
    current_user = await get_current_user(credentials)

    # Calculate date range
    days = int(period.replace('days', ''))
    end = datetime.now(UTC)
    start = end - timedelta(days=days)

    # Get charges
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'charge_category': {'$in': ['food', 'beverage']},
        'date': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Group by date
    daily_revenue = {}
    for charge in charges:
        date_str = charge.get('date', '')[:10]
        category = charge.get('charge_category')

        if date_str not in daily_revenue:
            daily_revenue[date_str] = {'food': 0, 'beverage': 0}

        daily_revenue[date_str][category] += charge.get('total', 0)

    # Prepare chart data
    chart_data = []
    current_date = start
    while current_date <= end:
        date_str = current_date.strftime('%Y-%m-%d')
        food = daily_revenue.get(date_str, {}).get('food', 0)
        beverage = daily_revenue.get(date_str, {}).get('beverage', 0)

        chart_data.append({
            'date': date_str,
            'food': round(food, 2),
            'beverage': round(beverage, 2),
            'total': round(food + beverage, 2)
        })

        current_date += timedelta(days=1)

    total_food = sum(d['food'] for d in chart_data)
    total_beverage = sum(d['beverage'] for d in chart_data)

    return {
        'period': period,
        'chart_data': chart_data,
        'summary': {
            'total_food': round(total_food, 2),
            'total_beverage': round(total_beverage, 2),
            'total_revenue': round(total_food + total_beverage, 2)
        }
    }


# ===== 5. MESSAGING MODULE (WHATSAPP / SMS / AUTO MESSAGES) =====



@router.post("/pos/create-order")
async def create_pos_order(
    data: POSOrderCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("pos")),  # v92 DW
):
    """Create a POS order with detailed items"""
    current_user = await get_current_user(credentials)

    if not data.order_items:
        raise HTTPException(status_code=400, detail="Order items required")

    # Get booking and guest info
    guest_id = None
    if data.booking_id:
        booking = await db.bookings.find_one({'id': data.booking_id, 'tenant_id': current_user.tenant_id})
        if booking:
            guest_id = booking['guest_id']

    # Build order items
    order_items_list = []
    subtotal = 0.0

    for item_data in data.order_items:
        # Get menu item
        menu_item = await db.pos_menu_items.find_one({
            'id': item_data.item_id,
            'tenant_id': current_user.tenant_id
        })

        if not menu_item:
            continue

        quantity = item_data.quantity
        total_price = menu_item['unit_price'] * quantity
        subtotal += total_price

        order_items_list.append(POSOrderItem(
            item_id=menu_item['id'],
            item_name=menu_item['item_name'],
            category=POSCategory(menu_item['category']),
            quantity=quantity,
            unit_price=menu_item['unit_price'],
            total_price=total_price
        ))

    # Calculate tax (18% VAT for Turkey)
    tax_amount = subtotal * 0.18
    total_amount = subtotal + tax_amount

    # Create order
    order = POSOrder(
        tenant_id=current_user.tenant_id,
        booking_id=data.booking_id,
        guest_id=guest_id,
        folio_id=data.folio_id,
        order_items=order_items_list,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        status="completed"
    )

    await db.pos_orders.insert_one(order.model_dump())

    # If folio_id provided, post charge to folio
    if data.folio_id:
        # Post charge to folio
        for order_item in order_items_list:
            charge = FolioCharge(
                tenant_id=current_user.tenant_id,
                folio_id=data.folio_id,
                charge_category=ChargeCategory.FOOD if order_item.category in ['food', 'dessert', 'appetizer'] else ChargeCategory.BEVERAGE,
                description=f"POS: {order_item.item_name} x {order_item.quantity}",
                quantity=order_item.quantity,
                unit_price=order_item.unit_price,
                amount=order_item.total_price,
                tax_amount=order_item.total_price * 0.18,
                total=order_item.total_price * 1.18,
                voided=False
            )

            await db.folio_charges.insert_one(charge.model_dump())

        # Update folio balance
        await recalculate_folio_balance(data.folio_id, current_user.tenant_id)

    return {
        'success': True,
        'message': 'POS order created',
        'order_id': order.id,
        'order': order.model_dump()
    }



# NOTE: GET /pos/orders moved to pos_router.py — canonical implementation
# reads from pos_menu_transactions (same source as Z-report) with legacy
# fallback to db.transactions and db.pos_orders. The duplicate that used to
# live here would have shadowed the canonical version with stale data.

# ============= MOBILE ENDPOINTS — MOVED to domains/pms/mobile_router.py =============

# ============================================================================
# FAZ 1 - HIZLI EKLENEBİLİR ÖZELLIKLER
# ============================================================================
# ============= GM DASHBOARD & ANALYTICS — MOVED to domains/revenue/analytics_router.py =============

# ============= MAINTENANCE TASKS ENDPOINT =============



@router.get("/pos/mobile/active-orders")
async def get_active_orders(
    status: str | None = None,  # pending, preparing, ready, served
    outlet_id: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get active F&B orders for mobile tracking
    Filters by status and outlet, calculates preparation time and delayed orders
    """
    current_user = await get_current_user(credentials)

    # Build query
    query = {
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['pending', 'preparing', 'ready']}  # Only active orders
    }

    if status:
        query['status'] = status

    if outlet_id:
        query['outlet_id'] = outlet_id

    # Get orders from pos_orders collection
    orders = []
    async for order in db.pos_orders.find(query).sort('created_at', 1):
        # Calculate time elapsed
        created_at = order.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

        time_elapsed = (datetime.now(UTC) - created_at).total_seconds() / 60  # minutes

        # Determine if delayed (more than 30 minutes in pending/preparing)
        is_delayed = False
        if order.get('status') in ['pending', 'preparing'] and time_elapsed > 30:
            is_delayed = True

        # Get table/room info
        table_number = order.get('table_number', 'N/A')
        room_number = order.get('room_number', 'N/A')

        orders.append({
            'id': order['id'],
            'order_number': order.get('order_number', order['id'][:8]),
            'status': order.get('status', 'pending'),
            'outlet_id': order.get('outlet_id', 'main_restaurant'),
            'outlet_name': order.get('outlet_name', 'Main Restaurant'),
            'table_number': table_number,
            'room_number': room_number,
            'guest_name': order.get('guest_name', 'Walk-in'),
            'items_count': len(order.get('order_items', [])),
            'total_amount': order.get('total_amount', 0),
            'time_elapsed_minutes': int(time_elapsed),
            'is_delayed': is_delayed,
            'created_at': order.get('created_at'),
            'notes': order.get('notes', '')
        })

    return {
        'orders': orders,
        'count': len(orders),
        'delayed_count': len([o for o in orders if o['is_delayed']])
    }


# 2. GET /api/pos/mobile/order/{order_id} - Get detailed order info


@router.get("/pos/mobile/order/{order_id}")
async def get_order_details(
    order_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get detailed information about a specific order
    Including items, notes, timing, and guest information
    """
    current_user = await get_current_user(credentials)

    order = await db.pos_orders.find_one({
        'id': order_id,
        'tenant_id': current_user.tenant_id
    })

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Calculate preparation time
    created_at = order.get('created_at')
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

    time_elapsed = (datetime.now(UTC) - created_at).total_seconds() / 60

    # Get order items with details
    order_items = []
    for item in order.get('order_items', []):
        order_items.append({
            'item_id': item.get('item_id'),
            'item_name': item.get('item_name', 'Unknown Item'),
            'category': item.get('category', 'food'),
            'quantity': item.get('quantity', 1),
            'unit_price': item.get('unit_price', 0),
            'total_price': item.get('total_price', 0),
            'special_instructions': item.get('special_instructions', '')
        })

    return {
        'id': order['id'],
        'order_number': order.get('order_number', order['id'][:8]),
        'status': order.get('status', 'pending'),
        'outlet_id': order.get('outlet_id'),
        'outlet_name': order.get('outlet_name', 'Main Restaurant'),
        'table_number': order.get('table_number', 'N/A'),
        'room_number': order.get('room_number', 'N/A'),
        'guest_name': order.get('guest_name', 'Walk-in'),
        'guest_id': order.get('guest_id'),
        'booking_id': order.get('booking_id'),
        'order_items': order_items,
        'subtotal': order.get('subtotal', 0),
        'tax_amount': order.get('tax_amount', 0),
        'total_amount': order.get('total_amount', 0),
        'payment_status': order.get('payment_status', 'unpaid'),
        'server_name': order.get('server_name', ''),
        'notes': order.get('notes', ''),
        'special_requests': order.get('special_requests', ''),
        'time_elapsed_minutes': int(time_elapsed),
        'created_at': order.get('created_at'),
        'updated_at': order.get('updated_at'),
        'status_history': order.get('status_history', [])
    }


# 3. PUT /api/pos/mobile/order/{order_id}/status - Update order status


@router.put("/pos/mobile/order/{order_id}/status")
async def update_order_status(
    order_id: str,
    request: UpdateOrderStatusRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("pos")),  # v92 DW
):
    """
    Update order status (pending → preparing → ready → served)
    Tracks status change history with timestamps
    """
    current_user = await get_current_user(credentials)

    # Validate status
    valid_statuses = ['pending', 'preparing', 'ready', 'served', 'cancelled']
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    # Get order
    order = await db.pos_orders.find_one({
        'id': order_id,
        'tenant_id': current_user.tenant_id
    })

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Add to status history
    status_history = order.get('status_history', [])
    status_history.append({
        'from_status': order.get('status', 'pending'),
        'to_status': request.status,
        'changed_by': current_user.username,
        'changed_by_role': current_user.role,
        'notes': request.notes,
        'timestamp': datetime.now(UTC).isoformat()
    })

    # Update order
    await db.pos_orders.update_one(
        {'id': order_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': request.status,
                'status_history': status_history,
                'updated_at': datetime.now(UTC).isoformat(),
                'updated_by': current_user.username
            }
        }
    )

    return {
        'message': 'Order status updated successfully',
        'order_id': order_id,
        'new_status': request.status,
        'updated_at': datetime.now(UTC).isoformat()
    }


# 4. GET /api/pos/mobile/order-history - Get order history with filters


@router.get("/pos/mobile/order-history")
async def get_order_history(
    start_date: str | None = None,
    end_date: str | None = None,
    outlet_id: str | None = None,
    server_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get order history with multiple filters
    Filters: date range, outlet, server, status
    """
    current_user = await get_current_user(credentials)

    # Build query
    query = {'tenant_id': current_user.tenant_id}

    # Date filter
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            # Add one day to include the end date
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
            date_filter['$lt'] = end_dt.isoformat()
        query['created_at'] = date_filter

    if outlet_id:
        query['outlet_id'] = outlet_id

    if server_name:
        query['server_name'] = server_name

    if status:
        query['status'] = status

    # Get orders
    orders = []
    async for order in db.pos_orders.find(query).sort('created_at', -1).limit(limit):
        orders.append({
            'id': order['id'],
            'order_number': order.get('order_number', order['id'][:8]),
            'status': order.get('status'),
            'outlet_name': order.get('outlet_name', 'Main Restaurant'),
            'table_number': order.get('table_number', 'N/A'),
            'guest_name': order.get('guest_name', 'Walk-in'),
            'items_count': len(order.get('order_items', [])),
            'total_amount': order.get('total_amount', 0),
            'server_name': order.get('server_name', ''),
            'created_at': order.get('created_at'),
            'payment_status': order.get('payment_status', 'unpaid')
        })

    return {
        'orders': orders,
        'count': len(orders),
        'filters_applied': {
            'start_date': start_date,
            'end_date': end_date,
            'outlet_id': outlet_id,
            'server_name': server_name,
            'status': status
        }
    }


# ============================================================================
# INVENTORY/STOCK MOBILE ENDPOINTS
# ============================================================================

# 5. GET /api/pos/mobile/inventory-movements - Get stock movements


@router.get("/pos/mobile/inventory-movements")
async def get_inventory_movements(
    start_date: str | None = None,
    end_date: str | None = None,
    product_id: str | None = None,
    movement_type: str | None = None,  # in, out, adjustment
    limit: int = 100,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get inventory/stock movements history
    Shows all ins/outs with date, product, quantity, type
    """
    current_user = await get_current_user(credentials)

    # Build query
    query = {'tenant_id': current_user.tenant_id}

    # Date filter
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = start_date
        if end_date:
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
            date_filter['$lt'] = end_dt.isoformat()
        query['timestamp'] = date_filter

    if product_id:
        query['product_id'] = product_id

    if movement_type:
        query['movement_type'] = movement_type

    # Get movements from inventory_movements collection
    movements = []
    async for movement in db.inventory_movements.find(query).sort('timestamp', -1).limit(limit):
        movements.append({
            'id': movement.get('id', str(uuid.uuid4())),
            'product_id': movement.get('product_id'),
            'product_name': movement.get('product_name', 'Unknown Product'),
            'movement_type': movement.get('movement_type', 'adjustment'),
            'quantity': movement.get('quantity', 0),
            'unit_of_measure': movement.get('unit_of_measure', 'pcs'),
            'reason': movement.get('reason', ''),
            'notes': movement.get('notes', ''),
            'performed_by': movement.get('performed_by', ''),
            'timestamp': movement.get('timestamp', datetime.now(UTC).isoformat())
        })

    # If no movements exist, create sample data
    if len(movements) == 0:
        sample_movements = [
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Coca Cola 33cl',
                'movement_type': 'in',
                'quantity': 50,
                'unit_of_measure': 'pcs',
                'reason': 'Tedarikçi teslimatı',
                'timestamp': (datetime.now(UTC) - timedelta(hours=2)).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Fanta 33cl',
                'movement_type': 'in',
                'quantity': 30,
                'unit_of_measure': 'pcs',
                'reason': 'Tedarikçi teslimatı',
                'timestamp': (datetime.now(UTC) - timedelta(hours=2)).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Coca Cola 33cl',
                'movement_type': 'out',
                'quantity': -12,
                'unit_of_measure': 'pcs',
                'reason': 'F&B satışı',
                'timestamp': (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Fanta 33cl',
                'movement_type': 'out',
                'quantity': -5,
                'unit_of_measure': 'pcs',
                'reason': 'F&B satışı',
                'timestamp': (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
            }
        ]
        movements = sample_movements

    return {
        'movements': movements,
        'count': len(movements)
    }


# 6. GET /api/pos/mobile/stock-levels - Get current stock levels


@router.get("/pos/mobile/stock-levels")
async def get_stock_levels(
    category: str | None = None,
    low_stock_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get current stock levels for all products
    Shows quantity, minimum level, and low stock warnings
    """
    current_user = await get_current_user(credentials)

    # Build query
    query = {'tenant_id': current_user.tenant_id}

    if category:
        query['category'] = category

    # Get stock items
    stock_items = []
    async for item in db.inventory.find(query):
        current_qty = item.get('quantity', 0)
        min_qty = item.get('minimum_quantity', 10)
        is_low_stock = current_qty <= min_qty

        # Calculate stock status
        if current_qty == 0:
            stock_status = 'out_of_stock'
            status_color = 'red'
        elif is_low_stock:
            stock_status = 'low'
            status_color = 'orange'
        elif current_qty <= min_qty * 2:
            stock_status = 'medium'
            status_color = 'yellow'
        else:
            stock_status = 'good'
            status_color = 'green'

        stock_item = {
            'id': item.get('id', str(uuid.uuid4())),
            'product_id': item.get('product_id', item.get('id')),
            'product_name': item.get('product_name', item.get('name', 'Unknown')),
            'category': item.get('category', 'general'),
            'current_quantity': current_qty,
            'minimum_quantity': min_qty,
            'unit_of_measure': item.get('unit_of_measure', 'pcs'),
            'is_low_stock': is_low_stock,
            'stock_status': stock_status,
            'status_color': status_color,
            'last_updated': item.get('last_updated', datetime.now(UTC).isoformat())
        }

        if not low_stock_only or is_low_stock:
            stock_items.append(stock_item)

    # If no items, create sample data
    if len(stock_items) == 0:
        sample_items = [
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Coca Cola 33cl',
                'category': 'beverage',
                'current_quantity': 38,
                'minimum_quantity': 20,
                'unit_of_measure': 'pcs',
                'is_low_stock': False,
                'stock_status': 'good',
                'status_color': 'green'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Fanta 33cl',
                'category': 'beverage',
                'current_quantity': 25,
                'minimum_quantity': 20,
                'unit_of_measure': 'pcs',
                'is_low_stock': False,
                'stock_status': 'medium',
                'status_color': 'yellow'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Sprite 33cl',
                'category': 'beverage',
                'current_quantity': 12,
                'minimum_quantity': 20,
                'unit_of_measure': 'pcs',
                'is_low_stock': True,
                'stock_status': 'low',
                'status_color': 'orange'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Ice Tea',
                'category': 'beverage',
                'current_quantity': 5,
                'minimum_quantity': 15,
                'unit_of_measure': 'pcs',
                'is_low_stock': True,
                'stock_status': 'low',
                'status_color': 'orange'
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Ayran',
                'category': 'beverage',
                'current_quantity': 0,
                'minimum_quantity': 10,
                'unit_of_measure': 'pcs',
                'is_low_stock': True,
                'stock_status': 'out_of_stock',
                'status_color': 'red'
            }
        ]

        if low_stock_only:
            stock_items = [item for item in sample_items if item['is_low_stock']]
        else:
            stock_items = sample_items

    return {
        'stock_items': stock_items,
        'count': len(stock_items),
        'low_stock_count': len([item for item in stock_items if item['is_low_stock']])
    }


# 7. GET /api/pos/mobile/low-stock-alerts - Get low stock alerts


@router.get("/pos/mobile/low-stock-alerts")
async def get_low_stock_alerts(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get products with low stock levels
    Critical alerts for inventory management
    """
    current_user = await get_current_user(credentials)

    # Get all inventory items
    query = {'tenant_id': current_user.tenant_id}

    low_stock_alerts = []
    async for item in db.inventory.find(query):
        current_qty = item.get('quantity', 0)
        min_qty = item.get('minimum_quantity', 10)

        if current_qty <= min_qty:
            # Calculate urgency
            if current_qty == 0:
                urgency = 'critical'
                urgency_level = 3
            elif current_qty <= min_qty * 0.5:
                urgency = 'high'
                urgency_level = 2
            else:
                urgency = 'medium'
                urgency_level = 1

            low_stock_alerts.append({
                'id': item.get('id', str(uuid.uuid4())),
                'product_id': item.get('product_id', item.get('id')),
                'product_name': item.get('product_name', item.get('name', 'Unknown')),
                'category': item.get('category', 'general'),
                'current_quantity': current_qty,
                'minimum_quantity': min_qty,
                'shortage': min_qty - current_qty,
                'unit_of_measure': item.get('unit_of_measure', 'pcs'),
                'urgency': urgency,
                'urgency_level': urgency_level,
                'alert_message': f"{item.get('product_name', 'Product')} → {current_qty} {item.get('unit_of_measure', 'pcs')} kaldı",
                'recommended_order': max(min_qty * 2 - current_qty, 0)
            })

    # Sort by urgency level (highest first)
    low_stock_alerts.sort(key=lambda x: x['urgency_level'], reverse=True)

    # If no alerts, create sample
    if len(low_stock_alerts) == 0:
        low_stock_alerts = [
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Sprite 33cl',
                'category': 'beverage',
                'current_quantity': 7,
                'minimum_quantity': 20,
                'shortage': 13,
                'unit_of_measure': 'pcs',
                'urgency': 'high',
                'urgency_level': 2,
                'alert_message': 'Sprite 33cl → 7 pcs kaldı',
                'recommended_order': 33
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Ice Tea',
                'category': 'beverage',
                'current_quantity': 5,
                'minimum_quantity': 15,
                'shortage': 10,
                'unit_of_measure': 'pcs',
                'urgency': 'high',
                'urgency_level': 2,
                'alert_message': 'Ice Tea → 5 pcs kaldı',
                'recommended_order': 25
            },
            {
                'id': str(uuid.uuid4()),
                'product_name': 'Ayran',
                'category': 'beverage',
                'current_quantity': 0,
                'minimum_quantity': 10,
                'shortage': 10,
                'unit_of_measure': 'pcs',
                'urgency': 'critical',
                'urgency_level': 3,
                'alert_message': 'Ayran → 0 pcs kaldı',
                'recommended_order': 20
            }
        ]

    return {
        'alerts': low_stock_alerts,
        'count': len(low_stock_alerts),
        'critical_count': len([a for a in low_stock_alerts if a['urgency'] == 'critical']),
        'high_count': len([a for a in low_stock_alerts if a['urgency'] == 'high'])
    }


# 8. POST /api/pos/mobile/stock-adjust - Adjust stock (Warehouse/F&B Manager only)


@router.post("/pos/mobile/stock-adjust")
async def adjust_stock(
    request: StockAdjustRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("pos")),  # v89 DW
):
    """
    Adjust stock levels (in/out/adjustment)
    Only for Warehouse staff and F&B Manager roles
    """
    current_user = await get_current_user(credentials)

    # Check permissions - only Warehouse and F&B Manager
    allowed_roles = ['admin', 'warehouse', 'fnb_manager', 'supervisor']
    if not _is_super_admin(current_user) and current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only Warehouse staff and F&B Manager can adjust stock."
        )

    # Validate adjustment type
    valid_types = ['in', 'out', 'adjustment']
    if request.adjustment_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid adjustment type. Must be one of: {', '.join(valid_types)}")

    # Get product
    product = await db.inventory.find_one({
        'id': request.product_id,
        'tenant_id': current_user.tenant_id
    })

    if not product:
        raise HTTPException(status_code=404, detail="Product not found in inventory")

    # Calculate new quantity
    current_qty = product.get('quantity', 0)

    if request.adjustment_type == 'in':
        new_qty = current_qty + request.quantity
    elif request.adjustment_type == 'out':
        new_qty = current_qty - request.quantity
        if new_qty < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock for this adjustment")
    else:  # adjustment
        new_qty = request.quantity  # Direct adjustment to specific quantity

    # Update inventory
    await db.inventory.update_one(
        {'id': request.product_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'quantity': new_qty,
                'last_updated': datetime.now(UTC).isoformat(),
                'last_updated_by': current_user.username
            }
        }
    )

    # Log the movement
    movement = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'product_id': request.product_id,
        'product_name': product.get('product_name', product.get('name', 'Unknown')),
        'movement_type': request.adjustment_type,
        'quantity': request.quantity if request.adjustment_type == 'in' else -request.quantity,
        'previous_quantity': current_qty,
        'new_quantity': new_qty,
        'unit_of_measure': product.get('unit_of_measure', 'pcs'),
        'reason': request.reason,
        'notes': request.notes,
        'performed_by': current_user.username,
        'performed_by_role': current_user.role,
        'timestamp': datetime.now(UTC).isoformat()
    }

    await db.inventory_movements.insert_one(movement)

    return {
        'message': 'Stock adjusted successfully',
        'product_id': request.product_id,
        'product_name': product.get('product_name', product.get('name')),
        'adjustment_type': request.adjustment_type,
        'quantity_changed': request.quantity,
        'previous_quantity': current_qty,
        'new_quantity': new_qty,
        'adjusted_by': current_user.name,
        'timestamp': movement['timestamp']
    }


# ============================================================================
# APPROVALS MODULE - Onay Mekanizmaları
# ============================================================================

# Approval Models


_ME_RECOMMENDATIONS = {
    'Stars':       'Yıldız ürün - menüde öne çıkar, kaliteyi koru, fiyat esnekliğini test et',
    'Plowhorses':  'İş ineği - maliyeti düşür (porsiyon/tedarikçi), üst-satış kombinasyonu öner',
    'Puzzles':     'Bulmaca - tanıtım/sunum iyileştir, menüde üst sıraya taşı, ad değiştir',
    'Dogs':        'Köpek - menüden çıkar veya tarifi yeniden tasarla',
}


@cached(ttl=180, key_prefix="menu_engineering")
async def _build_menu_engineering(
    tenant_id: str,
    start_iso: str,
    end_iso: str,
    outlet_id: str | None,
) -> dict[str, Any]:
    """Sprint 33 R9: Kasavana-Smith menu engineering matrisi.

    Popülerlik eşiği = (1 / N) × %70 (klasik menu-mix ortalaması).
    Karlılık eşiği = ağırlıklı ortalama katkı payı (CM/birim).
    """
    # 1) Menü kataloğu — fiyat + maliyet için
    catalog_raw = await db.pos_menu_items.find(
        {'tenant_id': tenant_id}, {'_id': 0}
    ).to_list(500)
    catalog: dict[str, dict[str, Any]] = {}
    for it in catalog_raw:
        nm = it.get('name') or it.get('item_name')
        if not nm:
            continue
        catalog[nm] = {
            'price': float(it.get('price', 0) or 0),
            'cost': float(it.get('cost', 0) or 0),
            'menu_category': it.get('category') or 'Diğer',
        }

    # 2) Sipariş satırlarını topla
    order_filter: dict[str, Any] = {
        'tenant_id': tenant_id,
        'created_at': {'$gte': start_iso, '$lte': end_iso},
    }
    if outlet_id:
        order_filter['outlet_id'] = outlet_id

    orders = await db.pos_orders.find(order_filter, {'_id': 0, 'items': 1}).to_list(20000)

    agg: dict[str, dict[str, float]] = {}
    for order in orders:
        for line in order.get('items', []) or []:
            nm = line.get('item_name') or line.get('name') or 'Bilinmiyor'
            qty = float(line.get('quantity', 1) or 1)
            line_price = float(line.get('price', 0) or 0)
            row = agg.setdefault(nm, {'qty': 0.0, 'revenue': 0.0})
            row['qty'] += qty
            row['revenue'] += qty * line_price

    if not agg:
        return {
            'period': {'start_date': start_iso[:10], 'end_date': end_iso[:10]},
            'outlet_id': outlet_id,
            'stars': 0, 'plowhorses': 0, 'puzzles': 0, 'dogs': 0,
            'menu_items': [],
            'thresholds': {'popularity_pct': 0, 'avg_cm_per_unit': 0},
            'totals': {'items': 0, 'units_sold': 0, 'revenue': 0.0, 'contribution_margin': 0.0},
        }

    # 3) Birim ekonomisi — fallback maliyet %35 food-cost varsayımı
    enriched = []
    total_qty = 0.0
    total_cm = 0.0
    for nm, row in agg.items():
        cat = catalog.get(nm, {})
        unit_price = cat.get('price') or (row['revenue'] / row['qty'] if row['qty'] else 0)
        unit_cost = cat.get('cost') or unit_price * 0.35
        cost_total = unit_cost * row['qty']
        cm_total = row['revenue'] - cost_total
        cm_per_unit = cm_total / row['qty'] if row['qty'] else 0
        margin_pct = (cm_total / row['revenue'] * 100) if row['revenue'] else 0
        enriched.append({
            '_name': nm,
            '_menu_cat': cat.get('menu_category', 'Diğer'),
            '_qty': row['qty'],
            '_revenue': row['revenue'],
            '_cost': cost_total,
            '_cm_total': cm_total,
            '_cm_unit': cm_per_unit,
            '_margin_pct': margin_pct,
            '_unit_price': unit_price,
            '_unit_cost': unit_cost,
        })
        total_qty += row['qty']
        total_cm += cm_total

    # 4) Eşikler
    n_items = len(enriched)
    pop_threshold_pct = (1.0 / n_items) * 70.0  # menu-mix klasik %70
    cm_threshold = (total_cm / total_qty) if total_qty else 0

    # 5) Sınıflandırma
    out_items = []
    counts = {'Stars': 0, 'Plowhorses': 0, 'Puzzles': 0, 'Dogs': 0}
    for e in enriched:
        pop_pct = (e['_qty'] / total_qty * 100) if total_qty else 0
        high_pop = pop_pct >= pop_threshold_pct
        high_cm = e['_cm_unit'] >= cm_threshold
        if high_pop and high_cm:
            cls = 'Stars'
        elif high_pop and not high_cm:
            cls = 'Plowhorses'
        elif not high_pop and high_cm:
            cls = 'Puzzles'
        else:
            cls = 'Dogs'
        counts[cls] += 1
        out_items.append({
            'item_name': e['_name'],
            'menu_category': e['_menu_cat'],
            'category': cls,                # frontend bunu rozet için kullanıyor
            'classification': cls,
            'quantity_sold': int(e['_qty']),
            'revenue': round(e['_revenue'], 2),
            'unit_price': round(e['_unit_price'], 2),
            'unit_cost': round(e['_unit_cost'], 2),
            'contribution_margin': round(e['_cm_total'], 2),
            'cm_per_unit': round(e['_cm_unit'], 2),
            'profit_margin': round(e['_margin_pct'], 1),
            'popularity_pct': round(pop_pct, 2),
            'recommendation': _ME_RECOMMENDATIONS[cls],
        })

    # Yıldızlar önce, köpekler sonra
    rank = {'Stars': 0, 'Puzzles': 1, 'Plowhorses': 2, 'Dogs': 3}
    out_items.sort(key=lambda x: (rank[x['classification']], -x['revenue']))

    return {
        'period': {'start_date': start_iso[:10], 'end_date': end_iso[:10]},
        'outlet_id': outlet_id,
        'stars': counts['Stars'],
        'plowhorses': counts['Plowhorses'],
        'puzzles': counts['Puzzles'],
        'dogs': counts['Dogs'],
        'menu_items': out_items,
        'thresholds': {
            'popularity_pct': round(pop_threshold_pct, 2),
            'avg_cm_per_unit': round(cm_threshold, 2),
            'method': 'Kasavana-Smith (1/N × 70% popülerlik, ağırlıklı CM ortalaması)',
        },
        'totals': {
            'items': n_items,
            'units_sold': int(total_qty),
            'revenue': round(sum(e['_revenue'] for e in enriched), 2),
            'contribution_margin': round(total_cm, 2),
        },
    }


@router.get("/pos/menu-engineering")
async def get_menu_engineering(
    start_date: str | None = None,
    end_date: str | None = None,
    outlet_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Menü mühendisliği matrisi (Stars / Plowhorses / Puzzles / Dogs).

    Kasavana-Smith metodu — gerçek `pos_orders` satışlarını `pos_menu_items`
    katalog maliyetleriyle birleştirir. Eşikler hardcoded değil; popülerlik
    eşiği (1/N)×%70, karlılık eşiği ağırlıklı ortalama katkı payı.
    """
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    return await _build_menu_engineering(
        current_user.tenant_id,
        start.isoformat(),
        end.isoformat(),
        outlet_id,
    )



