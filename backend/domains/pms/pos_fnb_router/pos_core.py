"""
pos_core

Auto-split sub-router (shared imports/classes inlined).
"""
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
from core.security import (
    get_current_user,
    security,
)
from models.enums import ChargeCategory
from models.schemas import CreatePOSTransactionRequest, FolioCharge, User
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_op  # v89 DW

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
    if not last_order:
        return 1
    try:
        return int(last_order[0].get('order_number', 0)) + 1
    except (TypeError, ValueError):
        return 1


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
    """F&B post sonrası bakiye yeniden hesabı — core helper'a delege (fail-closed)."""
    from core.utils import calculate_folio_balance
    return await calculate_folio_balance(folio_id, tenant_id)


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









# ============= PHOTO UPLOAD (KAT HİZMETLERİ İÇİN) =============






# rbac-allow: cache-rbac — POS F&B orders operasyonel

# ============= HOTEL INVENTORY MANAGEMENT =============
















# ============= CHANNEL MANAGER ENHANCEMENTS =============

























# ============= HOTEL INTERNAL MESSAGING =============














# ===== 5. MESSAGING MODULE (WHATSAPP / SMS / AUTO MESSAGES) =====






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





# 2. GET /api/pos/mobile/order/{order_id} - Get detailed order info




# 3. PUT /api/pos/mobile/order/{order_id}/status - Update order status




# 4. GET /api/pos/mobile/order-history - Get order history with filters




# ============================================================================
# INVENTORY/STOCK MOBILE ENDPOINTS
# ============================================================================

# 5. GET /api/pos/mobile/inventory-movements - Get stock movements




# 6. GET /api/pos/mobile/stock-levels - Get current stock levels




# 7. GET /api/pos/mobile/low-stock-alerts - Get low stock alerts




# 8. POST /api/pos/mobile/stock-adjust - Adjust stock (Warehouse/F&B Manager only)




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

router = APIRouter(prefix="/api", tags=["PMS / POS & F&B"])


# ── POST /pos/transaction ──
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
# ── POST /pos/check-split ──
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

        total_raw_indices = 0
        total_valid_indices = 0
        for split_num, item_indices in split_details.items():
            safe_indices = []
            for raw_idx in (item_indices or []):
                total_raw_indices += 1
                try:
                    idx_int = int(raw_idx)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx_int < len(items):
                    safe_indices.append(idx_int)
                    total_valid_indices += 1
            split_amount = sum(float(items[i].get('price', 0) or 0) for i in safe_indices)
            split_items = [items[i].get('name') for i in safe_indices]
            try:
                split_number = int(split_num)
            except (TypeError, ValueError):
                split_number = len(split_transactions) + 1
            split_transactions.append({
                'split_number': split_number,
                'amount': round(split_amount, 2),
                'items': split_items
            })

        if total_raw_indices > 0 and total_valid_indices == 0:
            raise HTTPException(
                status_code=400,
                detail="by_item split: no valid item indices in split_details (all out of range or non-numeric)"
            )

    elif split_type == 'custom':
        # Custom amounts
        if not split_details:
            raise HTTPException(status_code=400, detail="split_details required for custom split")

        for split_num, amount in split_details.items():
            try:
                amount_f = float(amount)
            except (TypeError, ValueError):
                amount_f = 0.0
            try:
                split_number = int(split_num)
            except (TypeError, ValueError):
                split_number = len(split_transactions) + 1
            split_transactions.append({
                'split_number': split_number,
                'amount': round(amount_f, 2),
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

    splits_total = round(sum(float(s.get('amount', 0) or 0) for s in split_transactions), 2)
    expected_total = round(float(total_amount or 0), 2)
    total_validation = {
        'expected': expected_total,
        'actual': splits_total,
        'delta': round(splits_total - expected_total, 2),
        'match': abs(splits_total - expected_total) < 0.01,
    }

    return {
        'success': True,
        'original_transaction_id': transaction_id,
        'original_amount': expected_total,
        'split_type': split_type,
        'split_count': len(split_transactions),
        'splits': split_transactions,
        'total_validation': total_validation,
    }
# ── POST /pos/transfer-table ──
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
# ── POST /pos/happy-hour ──
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
# ── GET /pos/table-layout/{outlet_id} ──
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
# ── POST /pos/table-layout/update ──
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
# ── GET /pos/split-bill-ui/{transaction_id} ──
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
# ── POST /pos/room-charge-restrictions ──
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
# ── POST /pos/validate-room-charge ──
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
# ── POST /pos/create-order ──
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
# ── GET /pos/menu-engineering ──
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
