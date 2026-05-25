"""
marketplace

Auto-split sub-router (shared imports/classes inlined).
"""
"""
PMS / POS & F&B Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.helpers import (
    require_feature,
)
from core.security import (
    get_current_user,
)
from models.schemas import Order, OrderCreate, User
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


# ── POST /marketplace/orders ──
@router.post("/marketplace/orders", response_model=Order, dependencies=[Depends(require_feature("hidden_marketplace"))])
async def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    order = Order(tenant_id=current_user.tenant_id, **order_data.model_dump())
    order_dict = order.model_dump()
    order_dict['created_at'] = order_dict['created_at'].isoformat()
    await db.orders.insert_one(order_dict)
    return order
# ── GET /marketplace/orders ──
@router.get("/marketplace/orders", response_model=list[Order], dependencies=[Depends(require_feature("hidden_marketplace"))])
@cached(ttl=300, key_prefix="marketplace_orders")  # Cache for 5 min
async def get_orders(current_user: User = Depends(get_current_user)):
    orders = await db.orders.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return orders
