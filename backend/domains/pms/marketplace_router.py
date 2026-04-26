"""
Domain Router: POS Marketplace

POS enhancements, warehouse procurement, marketplace extensions.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.helpers import require_feature
from core.security import get_current_user, security
from models.schemas import (
    AdjustInventoryRequest,
    ApprovePurchaseOrderRequest,
    CreateDeliveryRequest,
    CreateMarketplaceProductRequest,
    CreateMenuItemRequest,
    CreateOutletRequest,
    UpdateOutletRequest,
    CreatePOSTransactionWithMenuRequest,
    CreatePurchaseOrderRequest,
    CreateSupplierRequest,
    CreateWarehouseRequest,
    GenerateZReportRequest,
    ReceivePurchaseOrderRequest,
    RejectPurchaseOrderRequest,
    UpdateDeliveryStatusRequest,
    UpdateSupplierCreditRequest,
    User,
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_op  # v95 DW

router = APIRouter(prefix="/api", tags=["pos-marketplace"])

# ========================================

# 1. MULTI-OUTLET SUPPORT (Restaurant 1, Restaurant 2, Bar, etc.)
@router.get("/pos/outlets")
async def get_outlets(current_user: User = Depends(get_current_user)):
    """Get all F&B outlets"""
    outlets = await db.pos_outlets.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    # Get transaction counts per outlet
    for outlet in outlets:
        today_trans = await db.pos_menu_transactions.count_documents({
            'tenant_id': current_user.tenant_id,
            'outlet_id': outlet['id'],
            'transaction_date': datetime.now(UTC).date().isoformat()
        })
        outlet['today_transactions'] = today_trans

    return {'outlets': outlets, 'count': len(outlets)}

@router.post("/pos/outlets")
async def create_outlet(
    request: CreateOutletRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """Create new F&B outlet"""
    outlet = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'outlet_name': request.outlet_name,
        'outlet_type': request.outlet_type,
        'location': request.location,
        'capacity': request.capacity,
        'opening_hours': request.opening_hours,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat()
    }

    outlet_copy = outlet.copy()
    await db.pos_outlets.insert_one(outlet_copy)
    return outlet

@router.put("/pos/outlets/{outlet_id}")
async def update_outlet(
    outlet_id: str,
    request: UpdateOutletRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Update F&B outlet (name, type, location, capacity, hours, status)."""
    existing = await db.pos_outlets.find_one({
        'id': outlet_id,
        'tenant_id': current_user.tenant_id
    })
    if not existing:
        raise HTTPException(status_code=404, detail="Outlet not found")

    update_fields = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Guncellenecek alan yok")
    update_fields['updated_at'] = datetime.now(UTC).isoformat()

    await db.pos_outlets.update_one(
        {'id': outlet_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_fields}
    )
    updated = await db.pos_outlets.find_one(
        {'id': outlet_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )
    return updated

@router.delete("/pos/outlets/{outlet_id}")
async def delete_outlet(
    outlet_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Soft-delete: status='inactive' (siparis gecmisi korunur)."""
    existing = await db.pos_outlets.find_one({
        'id': outlet_id,
        'tenant_id': current_user.tenant_id
    })
    if not existing:
        raise HTTPException(status_code=404, detail="Outlet not found")

    await db.pos_outlets.update_one(
        {'id': outlet_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'inactive', 'deleted_at': datetime.now(UTC).isoformat()}}
    )
    return {'message': 'Outlet pasif duruma alindi', 'outlet_id': outlet_id}

@router.get("/pos/outlets/{outlet_id}")
async def get_outlet_details(
    outlet_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get outlet details with menu and stats"""
    outlet = await db.pos_outlets.find_one({
        'id': outlet_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Get menu items
    menu_items = await db.pos_menu_items.find({
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id
    }, {'_id': 0}).to_list(1000)

    # Get today's stats
    today = datetime.now(UTC).date().isoformat()
    today_transactions = await db.pos_menu_transactions.find({
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id,
        'transaction_date': today
    }, {'_id': 0}).to_list(1000)

    today_revenue = sum(t.get('total_amount', 0) for t in today_transactions)

    return {
        'outlet': outlet,
        'menu_items': menu_items,
        'menu_items_count': len(menu_items),
        'today_stats': {
            'transactions': len(today_transactions),
            'revenue': round(today_revenue, 2)
        }
    }


# 2. MENU-BASED TRANSACTION BREAKDOWN
@router.get("/pos/menu-items")
async def get_menu_items(
    outlet_id: str = None,
    category: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get menu items with optional filters"""
    query = {'tenant_id': current_user.tenant_id}

    if outlet_id:
        query['outlet_id'] = outlet_id
    if category:
        query['category'] = category

    menu_items = await db.pos_menu_items.find(query, {'_id': 0}).to_list(1000)

    return {'menu_items': menu_items, 'count': len(menu_items)}

@router.post("/pos/menu-items")
async def create_menu_item(
    request: CreateMenuItemRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    """Create menu item for outlet"""
    # Verify outlet exists
    outlet = await db.pos_outlets.find_one({
        'id': request.outlet_id,
        'tenant_id': current_user.tenant_id
    })

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    menu_item = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'outlet_id': request.outlet_id,
        'item_name': request.item_name,
        'category': request.category,
        'price': request.price,
        'cost': request.cost,
        'description': request.description,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat()
    }

    menu_copy = menu_item.copy()
    await db.pos_menu_items.insert_one(menu_copy)
    return menu_item

@router.post("/pos/transactions/with-menu")
async def create_pos_transaction_with_menu(
    request: CreatePOSTransactionWithMenuRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    """Create POS transaction with menu item breakdown"""
    # Verify outlet
    outlet = await db.pos_outlets.find_one({
        'id': request.outlet_id,
        'tenant_id': current_user.tenant_id
    })

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Calculate totals
    subtotal = sum(item.get('quantity', 0) * item.get('price', 0) for item in request.items)

    # Get menu item details and calculate costs
    enriched_items = []
    total_cost = 0

    for item in request.items:
        menu_item = await db.pos_menu_items.find_one({
            'id': item.get('menu_item_id'),
            'tenant_id': current_user.tenant_id
        }, {'_id': 0})

        if menu_item:
            item_cost = menu_item.get('cost', 0) * item.get('quantity', 0)
            total_cost += item_cost

            enriched_items.append({
                'menu_item_id': item.get('menu_item_id'),
                'item_name': menu_item.get('item_name'),
                'category': menu_item.get('category'),
                'quantity': item.get('quantity'),
                'unit_price': item.get('price'),
                'unit_cost': menu_item.get('cost', 0),
                'total_price': item.get('quantity') * item.get('price'),
                'total_cost': item_cost
            })

    # Create transaction
    transaction = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'outlet_id': request.outlet_id,
        'outlet_name': outlet.get('outlet_name'),
        'transaction_date': datetime.now(UTC).date().isoformat(),
        'transaction_time': datetime.now(UTC).time().isoformat(),
        'items': enriched_items,
        'subtotal': round(subtotal, 2),
        'total_amount': round(subtotal, 2),  # Can add tax/service charge
        'total_cost': round(total_cost, 2),
        'gross_profit': round(subtotal - total_cost, 2),
        'payment_method': request.payment_method,
        'folio_id': request.folio_id,
        'table_number': request.table_number,
        'server_name': request.server_name,
        'status': 'completed',
        'processed_by': current_user.id,
        'created_at': datetime.now(UTC).isoformat()
    }

    trans_copy = transaction.copy()
    await db.pos_menu_transactions.insert_one(trans_copy)

    # Post to folio if folio_id provided
    if request.folio_id:
        folio_charge = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'folio_id': request.folio_id,
            'charge_date': datetime.now(UTC).date().isoformat(),
            'description': f"F&B - {outlet.get('outlet_name')}",
            'category': 'fnb',
            'amount': subtotal,
            'quantity': 1,
            'total': subtotal,
            'voided': False,
            'posted_at': datetime.now(UTC).isoformat(),
            'posted_by': current_user.id
        }
        folio_copy = folio_charge.copy()
        await db.folio_charges.insert_one(folio_copy)

    return transaction

@router.get("/pos/menu-sales-breakdown")
async def get_menu_sales_breakdown(
    outlet_id: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get menu item sales breakdown"""
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = start_date

    # Get transactions
    query = {
        'tenant_id': current_user.tenant_id,
        'transaction_date': {'$gte': start_date, '$lte': end_date}
    }

    if outlet_id:
        query['outlet_id'] = outlet_id

    transactions = await db.pos_menu_transactions.find(query, {'_id': 0}).to_list(10000)

    # Aggregate by menu item
    menu_sales = {}
    category_sales = {}
    outlet_sales = {}

    for trans in transactions:
        outlet_name = trans.get('outlet_name', 'Unknown')
        outlet_sales[outlet_name] = outlet_sales.get(outlet_name, 0) + trans.get('total_amount', 0)

        for item in trans.get('items', []):
            item_name = item.get('item_name')
            category = item.get('category', 'Other')

            if item_name not in menu_sales:
                menu_sales[item_name] = {
                    'item_name': item_name,
                    'category': category,
                    'quantity_sold': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'gross_profit': 0
                }

            menu_sales[item_name]['quantity_sold'] += item.get('quantity', 0)
            menu_sales[item_name]['total_revenue'] += item.get('total_price', 0)
            menu_sales[item_name]['total_cost'] += item.get('total_cost', 0)
            menu_sales[item_name]['gross_profit'] += (item.get('total_price', 0) - item.get('total_cost', 0))

            category_sales[category] = category_sales.get(category, 0) + item.get('total_price', 0)

    # Sort by revenue
    sorted_menu_sales = sorted(menu_sales.values(), key=lambda x: x['total_revenue'], reverse=True)

    # Calculate totals
    total_revenue = sum(item['total_revenue'] for item in sorted_menu_sales)
    total_cost = sum(item['total_cost'] for item in sorted_menu_sales)

    return {
        'date_range': f"{start_date} to {end_date}",
        'menu_items': sorted_menu_sales,
        'by_category': [
            {'category': cat, 'revenue': round(rev, 2)}
            for cat, rev in sorted(category_sales.items(), key=lambda x: x[1], reverse=True)
        ],
        'by_outlet': [
            {'outlet_name': name, 'revenue': round(rev, 2)}
            for name, rev in sorted(outlet_sales.items(), key=lambda x: x[1], reverse=True)
        ],
        'summary': {
            'total_transactions': len(transactions),
            'total_revenue': round(total_revenue, 2),
            'total_cost': round(total_cost, 2),
            'gross_profit': round(total_revenue - total_cost, 2),
            'profit_margin': round((total_revenue - total_cost) / total_revenue * 100, 1) if total_revenue > 0 else 0
        }
    }


# 3. Z REPORT / GÜNLÜK KAPANIŞ
@router.post("/pos/z-report")
async def generate_z_report(
    request: GenerateZReportRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v99 DW
):
    """Generate Z Report (End of Day report)"""
    date = request.date or datetime.now(UTC).date().isoformat()
    outlet_id = request.outlet_id

    # Get transactions for the day
    query = {
        'tenant_id': current_user.tenant_id,
        'transaction_date': date
    }

    if outlet_id:
        query['outlet_id'] = outlet_id
        outlet = await db.pos_outlets.find_one({'id': outlet_id}, {'_id': 0})
        outlet_name = outlet.get('outlet_name') if outlet else 'Unknown'
    else:
        outlet_name = 'All Outlets'

    transactions = await db.pos_menu_transactions.find(query, {'_id': 0}).to_list(10000)

    if not transactions:
        return {
            'message': 'No transactions found for this date',
            'date': date,
            'outlet': outlet_name
        }

    # Calculate totals
    total_transactions = len(transactions)
    gross_sales = sum(t.get('total_amount', 0) for t in transactions)
    total_cost = sum(t.get('total_cost', 0) for t in transactions)
    gross_profit = gross_sales - total_cost

    # Payment method breakdown
    payment_methods = {}
    for trans in transactions:
        method = trans.get('payment_method', 'cash')
        payment_methods[method] = payment_methods.get(method, 0) + trans.get('total_amount', 0)

    # Category breakdown
    category_sales = {}
    menu_item_sales = {}

    for trans in transactions:
        for item in trans.get('items', []):
            category = item.get('category', 'Other')
            item_name = item.get('item_name')

            category_sales[category] = category_sales.get(category, 0) + item.get('total_price', 0)

            if item_name not in menu_item_sales:
                menu_item_sales[item_name] = {
                    'quantity': 0,
                    'revenue': 0
                }
            menu_item_sales[item_name]['quantity'] += item.get('quantity', 0)
            menu_item_sales[item_name]['revenue'] += item.get('total_price', 0)

    # Server breakdown
    server_sales = {}
    for trans in transactions:
        server = trans.get('server_name', 'Unknown')
        server_sales[server] = server_sales.get(server, 0) + trans.get('total_amount', 0)

    # Hourly breakdown
    hourly_sales = {}
    for trans in transactions:
        hour = trans.get('transaction_time', '00:00:00')[:2]
        hourly_sales[hour] = hourly_sales.get(hour, 0) + trans.get('total_amount', 0)

    # Top selling items
    top_items = sorted(
        [{'item': k, **v} for k, v in menu_item_sales.items()],
        key=lambda x: x['revenue'],
        reverse=True
    )[:10]

    # Create Z Report
    z_report = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'report_date': date,
        'outlet_id': outlet_id,
        'outlet_name': outlet_name,
        'report_type': 'Z-Report',
        'generated_at': datetime.now(UTC).isoformat(),
        'generated_by': current_user.id,

        # Summary
        'summary': {
            'total_transactions': total_transactions,
            'gross_sales': round(gross_sales, 2),
            'total_cost': round(total_cost, 2),
            'gross_profit': round(gross_profit, 2),
            'profit_margin': round((gross_profit / gross_sales * 100), 1) if gross_sales > 0 else 0,
            'average_check': round(gross_sales / total_transactions, 2) if total_transactions > 0 else 0
        },

        # Payment methods
        'payment_methods': [
            {'method': method, 'amount': round(amount, 2), 'count': sum(1 for t in transactions if t.get('payment_method') == method)}
            for method, amount in payment_methods.items()
        ],

        # Category breakdown
        'categories': [
            {'category': cat, 'revenue': round(rev, 2)}
            for cat, rev in sorted(category_sales.items(), key=lambda x: x[1], reverse=True)
        ],

        # Server performance
        'servers': [
            {'server_name': server, 'revenue': round(rev, 2)}
            for server, rev in sorted(server_sales.items(), key=lambda x: x[1], reverse=True)
        ],

        # Hourly sales
        'hourly_breakdown': [
            {'hour': f"{hour}:00", 'revenue': round(rev, 2)}
            for hour, rev in sorted(hourly_sales.items())
        ],

        # Top selling items
        'top_items': [
            {
                'item_name': item['item'],
                'quantity_sold': item['quantity'],
                'revenue': round(item['revenue'], 2)
            }
            for item in top_items
        ]
    }

    # Save Z Report
    z_copy = z_report.copy()
    await db.z_reports.insert_one(z_copy)

    return z_report

@router.get("/pos/z-reports")
async def get_z_reports(
    outlet_id: str = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get Z Reports history"""
    query = {'tenant_id': current_user.tenant_id}

    if outlet_id:
        query['outlet_id'] = outlet_id

    if start_date and end_date:
        query['report_date'] = {'$gte': start_date, '$lte': end_date}

    reports = await db.z_reports.find(
        query,
        {'_id': 0}
    ).sort('report_date', -1).to_list(100)

    return {'reports': reports, 'count': len(reports)}


# --------------------------------------------------------------------------
# F&B Mobile Management - Orders, Recipes, Stock Consumption
# --------------------------------------------------------------------------

@router.get("/fnb/mobile/outlets")
async def get_fnb_outlets_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all F&B outlets with details"""
    current_user = await get_current_user(credentials)

    outlets = []
    async for outlet in db.outlets.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }).sort('name', 1):
        outlets.append({
            'id': outlet.get('id'),
            'name': outlet.get('name'),
            'outlet_type': outlet.get('outlet_type'),
            'department': outlet.get('department'),
            'location': outlet.get('location'),
            'capacity': outlet.get('capacity'),
            'opening_time': outlet.get('opening_time'),
            'closing_time': outlet.get('closing_time'),
            'manager': outlet.get('manager'),
            'is_active': outlet.get('is_active', True)
        })

    return {
        'outlets': outlets,
        'count': len(outlets)
    }


@router.get("/fnb/mobile/orders/active")
async def get_active_orders_mobile(
    outlet_id: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get active POS orders (pending, preparing, ready)"""
    current_user = await get_current_user(credentials)

    query = {
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['pending', 'preparing', 'ready']}
    }

    if outlet_id:
        query['outlet_id'] = outlet_id

    orders = []
    total_value = 0.0

    async for order in db.pos_orders.find(query).sort('created_at', -1).limit(100):
        order_data = {
            'id': order.get('id'),
            'order_number': order.get('order_number'),
            'outlet_name': order.get('outlet_name'),
            'table_number': order.get('table_number'),
            'room_number': order.get('room_number'),
            'order_type': order.get('order_type'),
            'status': order.get('status'),
            'items_count': len(order.get('items', [])),
            'total': order.get('total', 0),
            'waiter': order.get('waiter'),
            'chef': order.get('chef'),
            'created_at': order.get('created_at').isoformat() if order.get('created_at') else None,
            'wait_time_minutes': None
        }

        # Calculate wait time
        if order.get('created_at'):
            wait_time = datetime.now(UTC) - order['created_at']
            order_data['wait_time_minutes'] = int(wait_time.total_seconds() / 60)

        orders.append(order_data)
        total_value += order.get('total', 0)

    # Summary by status
    summary = {
        'pending': len([o for o in orders if o['status'] == 'pending']),
        'preparing': len([o for o in orders if o['status'] == 'preparing']),
        'ready': len([o for o in orders if o['status'] == 'ready']),
        'total_orders': len(orders),
        'total_value': total_value,
        'average_wait_time': sum(o.get('wait_time_minutes', 0) for o in orders) / len(orders) if orders else 0
    }

    return {
        'orders': orders,
        'summary': summary
    }


@router.get("/fnb/mobile/orders/{order_id}")
async def get_order_detail_mobile(
    order_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get order detail with items"""
    current_user = await get_current_user(credentials)

    order = await db.pos_orders.find_one({
        'id': order_id,
        'tenant_id': current_user.tenant_id
    })

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        'order': {
            'id': order.get('id'),
            'order_number': order.get('order_number'),
            'outlet_name': order.get('outlet_name'),
            'table_number': order.get('table_number'),
            'room_number': order.get('room_number'),
            'order_type': order.get('order_type'),
            'status': order.get('status'),
            'items': order.get('items', []),
            'subtotal': order.get('subtotal', 0),
            'tax': order.get('tax', 0),
            'service_charge': order.get('service_charge', 0),
            'total': order.get('total', 0),
            'waiter': order.get('waiter'),
            'chef': order.get('chef'),
            'notes': order.get('notes'),
            'created_at': order.get('created_at').isoformat() if order.get('created_at') else None,
            'started_at': order.get('started_at').isoformat() if order.get('started_at') else None,
            'ready_at': order.get('ready_at').isoformat() if order.get('ready_at') else None,
            'served_at': order.get('served_at').isoformat() if order.get('served_at') else None
        }
    }


@router.post("/fnb/mobile/orders/{order_id}/status")
async def update_order_status_mobile(
    order_id: str,
    new_status: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("pos")),  # v92 DW
):
    """Update order status"""
    current_user = await get_current_user(credentials)

    order = await db.pos_orders.find_one({
        'id': order_id,
        'tenant_id': current_user.tenant_id
    })

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC)
    }

    if new_status == 'preparing' and not order.get('started_at'):
        update_data['started_at'] = datetime.now(UTC)
    elif new_status == 'ready' and not order.get('ready_at'):
        update_data['ready_at'] = datetime.now(UTC)
    elif new_status == 'served' and not order.get('served_at'):
        update_data['served_at'] = datetime.now(UTC)

    await db.pos_orders.update_one(
        {'id': order_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    return {
        'message': f'Order status updated to {new_status}',
        'order_id': order_id,
        'new_status': new_status
    }


@router.get("/fnb/mobile/recipes")
async def get_recipes_mobile(
    menu_item_id: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recipes with ingredient details"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if menu_item_id:
        query['menu_item_id'] = menu_item_id

    recipes = []
    async for recipe in db.recipes.find(query).sort('menu_item_name', 1):
        recipes.append({
            'id': recipe.get('id'),
            'menu_item_id': recipe.get('menu_item_id'),
            'menu_item_name': recipe.get('menu_item_name'),
            'ingredients': recipe.get('ingredients', []),
            'ingredient_count': len(recipe.get('ingredients', [])),
            'preparation_time_minutes': recipe.get('preparation_time_minutes'),
            'serving_size': recipe.get('serving_size', 1),
            'total_cost': recipe.get('total_cost', 0),
            'selling_price': recipe.get('selling_price', 0),
            'profit_margin': recipe.get('profit_margin', 0),
            'notes': recipe.get('notes')
        })

    return {
        'recipes': recipes,
        'count': len(recipes)
    }


@router.get("/fnb/mobile/ingredients")
async def get_ingredients_mobile(
    low_stock_only: bool = False,
    category: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get ingredient inventory"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if category:
        query['category'] = category

    ingredients = []
    low_stock_count = 0
    total_value = 0.0

    async for ingredient in db.ingredients.find(query).sort('name', 1):
        current_stock = ingredient.get('current_stock', 0)
        minimum_stock = ingredient.get('minimum_stock', 0)
        is_low_stock = current_stock <= minimum_stock

        if low_stock_only and not is_low_stock:
            continue

        if is_low_stock:
            low_stock_count += 1

        stock_value = current_stock * ingredient.get('unit_cost', 0)
        total_value += stock_value

        ingredients.append({
            'id': ingredient.get('id'),
            'name': ingredient.get('name'),
            'category': ingredient.get('category'),
            'unit': ingredient.get('unit'),
            'current_stock': current_stock,
            'minimum_stock': minimum_stock,
            'is_low_stock': is_low_stock,
            'unit_cost': ingredient.get('unit_cost', 0),
            'stock_value': stock_value,
            'supplier': ingredient.get('supplier'),
            'storage_location': ingredient.get('storage_location'),
            'expiry_date': ingredient.get('expiry_date').isoformat() if ingredient.get('expiry_date') else None,
            'last_restocked': ingredient.get('last_restocked').isoformat() if ingredient.get('last_restocked') else None
        })

    return {
        'ingredients': ingredients,
        'summary': {
            'total_count': len(ingredients),
            'low_stock_count': low_stock_count,
            'total_inventory_value': total_value,
            'categories': list({i['category'] for i in ingredients})
        }
    }


@router.get("/fnb/mobile/stock-consumption")
async def get_stock_consumption_mobile(
    outlet_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get stock consumption report"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if outlet_id:
        query['outlet_id'] = outlet_id

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter['$lte'] = datetime.fromisoformat(end_date)
        query['consumed_at'] = date_filter
    else:
        # Default to today
        today = datetime.now(UTC).date()
        start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)
        query['consumed_at'] = {'$gte': start_of_day, '$lte': end_of_day}

    consumptions = []
    total_cost = 0.0
    by_ingredient = {}
    by_outlet = {}

    async for consumption in db.stock_consumption.find(query).sort('consumed_at', -1):
        ingredient_name = consumption.get('ingredient_name')
        outlet_name = consumption.get('outlet_name')
        cost = consumption.get('cost', 0)
        quantity = consumption.get('consumed_quantity', 0)

        consumptions.append({
            'id': consumption.get('id'),
            'ingredient_name': ingredient_name,
            'consumed_quantity': quantity,
            'unit': consumption.get('unit'),
            'outlet_name': outlet_name,
            'cost': cost,
            'consumed_at': consumption.get('consumed_at').isoformat() if consumption.get('consumed_at') else None
        })

        total_cost += cost

        # Aggregate by ingredient
        if ingredient_name not in by_ingredient:
            by_ingredient[ingredient_name] = {'quantity': 0, 'cost': 0}
        by_ingredient[ingredient_name]['quantity'] += quantity
        by_ingredient[ingredient_name]['cost'] += cost

        # Aggregate by outlet
        if outlet_name not in by_outlet:
            by_outlet[outlet_name] = {'cost': 0, 'item_count': 0}
        by_outlet[outlet_name]['cost'] += cost
        by_outlet[outlet_name]['item_count'] += 1

    return {
        'consumptions': consumptions,
        'summary': {
            'total_items': len(consumptions),
            'total_cost': total_cost,
            'by_ingredient': by_ingredient,
            'by_outlet': by_outlet
        }
    }


@router.get("/fnb/mobile/daily-summary")
async def get_fnb_daily_summary_mobile(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comprehensive F&B daily summary"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date).date()
    else:
        target_date = datetime.now(UTC).date()

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

    # Orders summary
    orders_query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    }

    total_orders = 0
    total_revenue = 0.0
    orders_by_outlet = {}
    orders_by_status = {'pending': 0, 'preparing': 0, 'ready': 0, 'served': 0, 'cancelled': 0}

    async for order in db.pos_orders.find(orders_query):
        total_orders += 1
        total_revenue += order.get('total', 0)

        outlet = order.get('outlet_name', 'Unknown')
        if outlet not in orders_by_outlet:
            orders_by_outlet[outlet] = {'count': 0, 'revenue': 0}
        orders_by_outlet[outlet]['count'] += 1
        orders_by_outlet[outlet]['revenue'] += order.get('total', 0)

        status = order.get('status', 'pending')
        orders_by_status[status] = orders_by_status.get(status, 0) + 1

    # Stock consumption summary
    consumption_query = {
        'tenant_id': current_user.tenant_id,
        'consumed_at': {'$gte': start_of_day, '$lte': end_of_day}
    }

    total_consumption_cost = 0.0
    consumption_count = 0

    async for consumption in db.stock_consumption.find(consumption_query):
        total_consumption_cost += consumption.get('cost', 0)
        consumption_count += 1

    # Calculate profit
    gross_profit = total_revenue - total_consumption_cost
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    return {
        'date': target_date.isoformat(),
        'orders': {
            'total_count': total_orders,
            'total_revenue': total_revenue,
            'by_outlet': orders_by_outlet,
            'by_status': orders_by_status,
            'average_order_value': total_revenue / total_orders if total_orders > 0 else 0
        },
        'stock_consumption': {
            'total_cost': total_consumption_cost,
            'item_count': consumption_count
        },
        'profitability': {
            'revenue': total_revenue,
            'cost': total_consumption_cost,
            'gross_profit': gross_profit,
            'profit_margin_percentage': profit_margin
        }
    }


# ========================================

@router.get("/marketplace/products", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def get_marketplace_products(
    category: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get marketplace product catalog"""
    query = {}
    if category:
        query['category'] = category

    products = await db.marketplace_products.find(
        query,
        {'_id': 0}
    ).to_list(1000)

    return {'products': products, 'count': len(products)}

@router.post("/marketplace/products")
async def create_marketplace_product(
    request: CreateMarketplaceProductRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Add product to marketplace catalog"""
    product = {
        'id': str(uuid.uuid4()),
        'product_name': request.product_name,
        'category': request.category,
        'unit_price': request.unit_price,
        'unit_of_measure': request.unit_of_measure,
        'supplier': request.supplier,
        'min_order_qty': request.min_order_qty,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat()
    }

    product_copy = product.copy()
    await db.marketplace_products.insert_one(product_copy)
    return product

@router.get("/marketplace/inventory")
async def get_inventory(
    location: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get current inventory levels"""
    query = {'tenant_id': current_user.tenant_id}
    if location:
        query['location'] = location

    inventory = await db.inventory.find(
        query,
        {'_id': 0}
    ).to_list(1000)

    return {'inventory': inventory, 'count': len(inventory)}

@router.post("/marketplace/inventory/adjust")
async def adjust_inventory(
    request: AdjustInventoryRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Adjust inventory quantity"""
    # Get current inventory
    inventory = await db.inventory.find_one({
        'tenant_id': current_user.tenant_id,
        'product_id': request.product_id,
        'location': request.location
    })
    quantity_change = request.quantity_change

    if not inventory:
        # Create new inventory record
        inventory = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'product_id': request.product_id,
            'location': request.location,
            'quantity': max(0, request.quantity_change),
            'updated_at': datetime.now(UTC).isoformat()
        }
        await db.inventory.insert_one(inventory)
    else:
        # Update existing inventory
        new_qty = max(0, inventory['quantity'] + quantity_change)
        await db.inventory.update_one(
            {'id': inventory['id']},
            {
                '$set': {
                    'quantity': new_qty,
                    'updated_at': datetime.now(UTC).isoformat()
                }
            }
        )

    # Log adjustment
    log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'product_id': request.product_id,
        'location': request.location,
        'quantity_change': request.quantity_change,
        'reason': request.reason,
        'adjusted_by': current_user.id,
        'adjusted_at': datetime.now(UTC).isoformat()
    }
    await db.inventory_adjustments.insert_one(log)

    return {'message': 'Inventory adjusted successfully'}

@router.get("/marketplace/purchase-orders")
async def get_purchase_orders(
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get purchase orders"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    orders = await db.purchase_orders.find(
        query,
        {'_id': 0}
    ).sort('created_at', -1).to_list(100)

    return {'orders': orders, 'count': len(orders)}

@router.post("/marketplace/purchase-orders", dependencies=[Depends(require_feature("hidden_marketplace"))])
async def create_purchase_order(
    request: CreatePurchaseOrderRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create purchase order"""
    # Calculate total
    total_amount = sum(item.get('quantity', 0) * item.get('unit_price', 0) for item in request.items)

    po = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'po_number': f"PO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}",
        'supplier': request.supplier,
        'items': request.items,
        'delivery_location': request.delivery_location,
        'expected_delivery_date': request.expected_delivery_date,
        'total_amount': round(total_amount, 2),
        'status': 'pending',
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    po_copy = po.copy()
    await db.purchase_orders.insert_one(po_copy)
    return po

@router.post("/marketplace/purchase-orders/{po_id}/approve")
async def approve_purchase_order(
    po_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    """Approve purchase order"""
    po = await db.purchase_orders.find_one({
        'id': po_id,
        'tenant_id': current_user.tenant_id
    })

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    await db.purchase_orders.update_one(
        {'id': po_id},
        {
            '$set': {
                'status': 'approved',
                'approved_at': datetime.now(UTC).isoformat(),
                'approved_by': current_user.id
            }
        }
    )

    return {'message': 'Purchase order approved successfully'}

@router.post("/marketplace/purchase-orders/{po_id}/receive")
async def receive_purchase_order(
    po_id: str,
    request: ReceivePurchaseOrderRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Receive purchase order and update inventory"""
    received_items = request.received_items
    po = await db.purchase_orders.find_one({
        'id': po_id,
        'tenant_id': current_user.tenant_id
    })

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    # Update inventory for received items
    for item in received_items:
        await db.inventory.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'product_id': item['product_id'],
                'location': po['delivery_location']
            },
            {
                '$inc': {'quantity': item['quantity_received']},
                '$set': {'updated_at': datetime.now(UTC).isoformat()}
            },
            upsert=True
        )

    # Update PO status
    await db.purchase_orders.update_one(
        {'id': po_id},
        {
            '$set': {
                'status': 'received',
                'received_at': datetime.now(UTC).isoformat(),
                'received_by': current_user.id,
                'received_items': received_items
            }
        }
    )

    return {'message': 'Purchase order received and inventory updated'}

@router.get("/marketplace/deliveries")
async def get_deliveries(
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get delivery tracking"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    deliveries = await db.deliveries.find(
        query,
        {'_id': 0}
    ).sort('created_at', -1).to_list(100)

    return {'deliveries': deliveries, 'count': len(deliveries)}

@router.post("/marketplace/deliveries")
async def create_delivery(
    request: CreateDeliveryRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create delivery tracking"""
    delivery = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'po_id': request.po_id,
        'tracking_number': request.tracking_number,
        'carrier': request.carrier,
        'estimated_delivery': request.estimated_delivery,
        'status': 'in_transit',
        'created_at': datetime.now(UTC).isoformat()
    }

    delivery_copy = delivery.copy()
    await db.deliveries.insert_one(delivery_copy)
    return delivery

@router.get("/marketplace/stock-alerts")
async def get_stock_alerts(current_user: User = Depends(get_current_user)):
    """Get low stock alerts"""
    # Get all inventory items
    inventory_items = await db.inventory.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(1000)

    alerts = []
    for item in inventory_items:
        # Get product details
        product = await db.marketplace_products.find_one(
            {'id': item['product_id']},
            {'_id': 0}
        )

        if product:
            # Check if below minimum (using min_order_qty * 2 as threshold)
            threshold = product.get('min_order_qty', 1) * 2
            if item['quantity'] < threshold:
                alerts.append({
                    'product_id': item['product_id'],
                    'product_name': product['product_name'],
                    'location': item['location'],
                    'current_quantity': item['quantity'],
                    'threshold': threshold,
                    'status': 'low_stock'
                })

    return {'alerts': alerts, 'count': len(alerts)}


# ========================================

# 1. SUPPLIER MANAGEMENT WITH CREDIT LIMITS
@router.get("/marketplace/suppliers")
async def get_suppliers(
    status: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get all suppliers with credit limit info"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    suppliers = await db.suppliers.find(
        query,
        {'_id': 0}
    ).to_list(100)

    return {'suppliers': suppliers, 'count': len(suppliers)}

@router.post("/marketplace/suppliers")
async def create_supplier(
    request: CreateSupplierRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create new supplier with credit limit"""
    supplier = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'supplier_name': request.supplier_name,
        'contact_person': request.contact_person,
        'contact_email': request.contact_email,
        'contact_phone': request.contact_phone,
        'credit_limit': request.credit_limit,
        'current_outstanding': 0.0,
        'available_credit': request.credit_limit,
        'payment_terms': request.payment_terms,
        'status': request.status,
        'created_at': datetime.now(UTC).isoformat()
    }

    supplier_copy = supplier.copy()
    await db.suppliers.insert_one(supplier_copy)
    return supplier

@router.put("/marketplace/suppliers/{supplier_id}/credit")
async def update_supplier_credit(
    supplier_id: str,
    request: UpdateSupplierCreditRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Update supplier credit limit and payment terms"""
    supplier = await db.suppliers.find_one({
        'id': supplier_id,
        'tenant_id': current_user.tenant_id
    })

    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Update available credit based on outstanding
    available_credit = request.credit_limit - supplier.get('current_outstanding', 0.0)

    await db.suppliers.update_one(
        {'id': supplier_id},
        {
            '$set': {
                'credit_limit': request.credit_limit,
                'available_credit': available_credit,
                'payment_terms': request.payment_terms,
                'updated_at': datetime.now(UTC).isoformat()
            }
        }
    )

    return {
        'message': 'Supplier credit updated successfully',
        'credit_limit': request.credit_limit,
        'available_credit': available_credit
    }

@router.get("/marketplace/suppliers/{supplier_id}/credit-status")
async def get_supplier_credit_status(
    supplier_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get supplier credit status and outstanding balance"""
    supplier = await db.suppliers.find_one(
        {'id': supplier_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )

    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Get all outstanding purchase orders
    outstanding_pos = await db.purchase_orders.find({
        'tenant_id': current_user.tenant_id,
        'supplier': supplier['supplier_name'],
        'status': {'$in': ['approved', 'received']},
        'payment_status': {'$ne': 'paid'}
    }, {'_id': 0}).to_list(100)

    total_outstanding = sum(po.get('total_amount', 0) for po in outstanding_pos)

    return {
        'supplier_id': supplier_id,
        'supplier_name': supplier['supplier_name'],
        'credit_limit': supplier.get('credit_limit', 0.0),
        'current_outstanding': total_outstanding,
        'available_credit': supplier.get('credit_limit', 0.0) - total_outstanding,
        'payment_terms': supplier.get('payment_terms', 'Net 30'),
        'outstanding_orders': len(outstanding_pos)
    }


# 2. GM APPROVAL WORKFLOW FOR PURCHASE ORDERS
@router.post("/marketplace/purchase-orders/{po_id}/submit-for-approval")
async def submit_po_for_approval(
    po_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Submit purchase order for GM approval"""
    po = await db.purchase_orders.find_one({
        'id': po_id,
        'tenant_id': current_user.tenant_id
    })

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if po.get('status') != 'pending':
        raise HTTPException(status_code=400, detail="Only pending orders can be submitted for approval")

    # Update PO status to awaiting_approval
    await db.purchase_orders.update_one(
        {'id': po_id},
        {
            '$set': {
                'status': 'awaiting_approval',
                'submitted_for_approval_at': datetime.now(UTC).isoformat(),
                'submitted_by': current_user.id
            }
        }
    )

    # Create approval request record
    approval_request = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'po_id': po_id,
        'po_number': po.get('po_number'),
        'total_amount': po.get('total_amount'),
        'supplier': po.get('supplier'),
        'status': 'pending',
        'requested_by': current_user.id,
        'requested_at': datetime.now(UTC).isoformat()
    }

    approval_copy = approval_request.copy()
    await db.approval_requests.insert_one(approval_copy)

    return {
        'message': 'Purchase order submitted for GM approval',
        'approval_request_id': approval_request['id']
    }

@router.get("/marketplace/approvals/pending")
async def get_pending_approvals(current_user: User = Depends(get_current_user)):
    """Get all pending approval requests (for GM)"""
    approvals = await db.approval_requests.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending'
    }, {'_id': 0}).sort('requested_at', -1).to_list(100)

    return {'approvals': approvals, 'count': len(approvals)}

@router.post("/marketplace/purchase-orders/{po_id}/approve")
async def approve_purchase_order_by_gm(
    po_id: str,
    request: ApprovePurchaseOrderRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    """GM approves purchase order"""
    po = await db.purchase_orders.find_one({
        'id': po_id,
        'tenant_id': current_user.tenant_id
    })

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    # Check user has GM/approval permission
    # (In production, add proper permission check here)

    # Update PO status
    await db.purchase_orders.update_one(
        {'id': po_id},
        {
            '$set': {
                'status': 'approved',
                'approved_at': datetime.now(UTC).isoformat(),
                'approved_by': current_user.id,
                'approval_notes': request.approval_notes
            }
        }
    )

    # Update approval request
    await db.approval_requests.update_one(
        {'po_id': po_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'approved',
                'approved_by': current_user.id,
                'approved_at': datetime.now(UTC).isoformat(),
                'notes': request.approval_notes
            }
        }
    )

    # Update supplier outstanding balance
    supplier = await db.suppliers.find_one({
        'tenant_id': current_user.tenant_id,
        'supplier_name': po.get('supplier')
    })

    if supplier:
        new_outstanding = supplier.get('current_outstanding', 0.0) + po.get('total_amount', 0.0)
        await db.suppliers.update_one(
            {'id': supplier['id']},
            {
                '$set': {
                    'current_outstanding': new_outstanding,
                    'available_credit': supplier.get('credit_limit', 0.0) - new_outstanding
                }
            }
        )

    return {'message': 'Purchase order approved successfully'}

@router.post("/marketplace/purchase-orders/{po_id}/reject")
async def reject_purchase_order(
    po_id: str,
    request: RejectPurchaseOrderRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    """GM rejects purchase order"""
    po = await db.purchase_orders.find_one({
        'id': po_id,
        'tenant_id': current_user.tenant_id
    })

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    await db.purchase_orders.update_one(
        {'id': po_id},
        {
            '$set': {
                'status': 'rejected',
                'rejected_at': datetime.now(UTC).isoformat(),
                'rejected_by': current_user.id,
                'rejection_reason': request.rejection_reason
            }
        }
    )

    await db.approval_requests.update_one(
        {'po_id': po_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'rejected',
                'rejected_by': current_user.id,
                'rejected_at': datetime.now(UTC).isoformat(),
                'rejection_reason': request.rejection_reason
            }
        }
    )

    return {'message': 'Purchase order rejected', 'reason': request.rejection_reason}


# 3. WAREHOUSE / DEPOT STOCK TRACKING
@router.get("/marketplace/warehouses")
async def get_warehouses(current_user: User = Depends(get_current_user)):
    """Get all warehouses/depots"""
    warehouses = await db.warehouses.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    return {'warehouses': warehouses, 'count': len(warehouses)}

@router.post("/marketplace/warehouses")
async def create_warehouse(
    request: CreateWarehouseRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create new warehouse/depot"""
    warehouse = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'warehouse_name': request.warehouse_name,
        'location': request.location,
        'capacity': request.capacity,
        'warehouse_type': request.warehouse_type,
        'current_stock_count': 0,
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat()
    }

    warehouse_copy = warehouse.copy()
    await db.warehouses.insert_one(warehouse_copy)
    return warehouse

@router.get("/marketplace/warehouses/{warehouse_id}/inventory")
async def get_warehouse_inventory(
    warehouse_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get inventory for specific warehouse"""
    warehouse = await db.warehouses.find_one({
        'id': warehouse_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Get all inventory items for this warehouse
    inventory = await db.inventory.find({
        'tenant_id': current_user.tenant_id,
        'location': warehouse['warehouse_name']
    }, {'_id': 0}).to_list(1000)

    # Enrich with product details
    for item in inventory:
        product = await db.marketplace_products.find_one(
            {'id': item['product_id']},
            {'_id': 0}
        )
        if product:
            item['product_name'] = product.get('product_name')
            item['category'] = product.get('category')
            item['unit_of_measure'] = product.get('unit_of_measure')

    total_items = sum(item.get('quantity', 0) for item in inventory)

    return {
        'warehouse': warehouse,
        'inventory': inventory,
        'total_items': total_items,
        'item_count': len(inventory)
    }

@router.get("/marketplace/stock-summary")
async def get_stock_summary_by_warehouse(current_user: User = Depends(get_current_user)):
    """Get stock summary across all warehouses"""
    warehouses = await db.warehouses.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    summary = []
    for warehouse in warehouses:
        inventory = await db.inventory.find({
            'tenant_id': current_user.tenant_id,
            'location': warehouse['warehouse_name']
        }, {'_id': 0}).to_list(1000)

        total_items = sum(item.get('quantity', 0) for item in inventory)
        unique_products = len(inventory)

        summary.append({
            'warehouse_id': warehouse['id'],
            'warehouse_name': warehouse['warehouse_name'],
            'location': warehouse['location'],
            'total_items': total_items,
            'unique_products': unique_products,
            'capacity': warehouse.get('capacity', 0),
            'utilization': round((total_items / warehouse.get('capacity', 1)) * 100, 1) if warehouse.get('capacity') else 0
        })

    return {'summary': summary, 'warehouse_count': len(warehouses)}


# 4. SHIPPING & DELIVERY TRACKING WITH CARRIER
@router.put("/marketplace/deliveries/{delivery_id}/update-status")
async def update_delivery_status(
    delivery_id: str,
    request: UpdateDeliveryStatusRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Update delivery status with location tracking"""
    delivery = await db.deliveries.find_one({
        'id': delivery_id,
        'tenant_id': current_user.tenant_id
    })

    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    # Create tracking event
    tracking_event = {
        'status': request.status,
        'location': request.location,
        'notes': request.notes,
        'timestamp': datetime.now(UTC).isoformat(),
        'updated_by': current_user.id
    }

    # Update delivery
    await db.deliveries.update_one(
        {'id': delivery_id},
        {
            '$set': {
                'status': request.status,
                'current_location': request.location,
                'updated_at': datetime.now(UTC).isoformat()
            },
            '$push': {
                'tracking_history': tracking_event
            }
        }
    )

    # If delivered, update PO status
    if request.status == 'delivered':
        await db.deliveries.update_one(
            {'id': delivery_id},
            {'$set': {'delivered_at': datetime.now(UTC).isoformat()}}
        )

    return {
        'message': 'Delivery status updated successfully',
        'new_status': request.status,
        'tracking_event': tracking_event
    }

@router.get("/marketplace/deliveries/{delivery_id}/tracking")
async def get_delivery_tracking(
    delivery_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get full tracking history for delivery"""
    delivery = await db.deliveries.find_one({
        'id': delivery_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    # Get associated PO
    po = await db.purchase_orders.find_one({
        'id': delivery.get('po_id')
    }, {'_id': 0})

    return {
        'delivery': delivery,
        'purchase_order': po,
        'tracking_history': delivery.get('tracking_history', []),
        'current_status': delivery.get('status'),
        'estimated_delivery': delivery.get('estimated_delivery')
    }

@router.get("/marketplace/deliveries/in-transit")
async def get_in_transit_deliveries(current_user: User = Depends(get_current_user)):
    """Get all in-transit deliveries"""
    deliveries = await db.deliveries.find({
        'tenant_id': current_user.tenant_id,
        'status': 'in_transit'
    }, {'_id': 0}).sort('estimated_delivery', 1).to_list(100)

    return {'deliveries': deliveries, 'count': len(deliveries)}


