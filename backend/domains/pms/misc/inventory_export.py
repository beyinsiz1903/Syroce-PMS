"""Auto-split from misc_router.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.enums import Permission
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from ._common import (
    cached,
    get_folio_details,
    has_permission,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()

# ============= GUEST MANAGEMENT =============

# ============= PMS - BOOKINGS MANAGEMENT =============



@sub_router.get("/inventory/alerts")
async def get_inventory_alerts(current_user: User = Depends(get_current_user)):
    """Get low stock and critical stock alerts"""
    from domains.pms.hotel_inventory_system import get_suggested_orders

    suggestions = await get_suggested_orders(db, current_user.tenant_id)

    return {
        'alerts': suggestions,
        'total_alerts': len(suggestions),
        'urgent_count': len([s for s in suggestions if s['priority'] == 'URGENT']),
        'high_count': len([s for s in suggestions if s['priority'] == 'HIGH'])
    }



@sub_router.get("/inventory/consumption-report")
async def get_consumption_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get inventory consumption report"""
    query = {
        'tenant_id': current_user.tenant_id,
        'movement_type': 'out'
    }

    # Add date filter if provided
    if start_date:
        query['created_at'] = {'$gte': start_date}
    if end_date:
        if 'created_at' not in query:
            query['created_at'] = {}
        query['created_at']['$lte'] = end_date

    movements = await db.stock_movements.find(query, {'_id': 0}).to_list(10000)

    # Group by item
    consumption_by_item = {}
    for movement in movements:
        item_id = movement['item_id']
        if item_id not in consumption_by_item:
            item = await db.inventory_items.find_one({'id': item_id}, {'_id': 0})
            if item:
                consumption_by_item[item_id] = {
                    'item_name': item['name'],
                    'total_quantity': 0,
                    'total_cost': 0,
                    'movement_count': 0
                }

        if item_id in consumption_by_item:
            consumption_by_item[item_id]['total_quantity'] += movement['quantity']
            consumption_by_item[item_id]['total_cost'] += movement['quantity'] * movement.get('unit_cost', 0)
            consumption_by_item[item_id]['movement_count'] += 1

    return {
        'period': {
            'start': start_date,
            'end': end_date
        },
        'consumption': list(consumption_by_item.values()),
        'total_movements': len(movements)
    }



@sub_router.post("/inventory/seed-hotel-amenities")
async def seed_hotel_amenities(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Seed database with common hotel amenities"""
    amenities = [
        {"name": "Şampuan", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 200, "unit_cost": 2.5, "reorder_level": 50},
        {"name": "Duş Jeli", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 200, "unit_cost": 2.5, "reorder_level": 50},
        {"name": "Terlik", "category": "Oda Ürünleri", "unit": "çift", "quantity": 100, "unit_cost": 5.0, "reorder_level": 30},
        {"name": "Islak Mendil", "category": "Banyo Ürünleri", "unit": "paket", "quantity": 150, "unit_cost": 1.5, "reorder_level": 40},
        {"name": "Diş Fırçası", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 180, "unit_cost": 1.0, "reorder_level": 50},
        {"name": "Tıraş Seti", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 80, "unit_cost": 3.0, "reorder_level": 30},
        {"name": "Duş Bonesi", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 200, "unit_cost": 0.5, "reorder_level": 60},
        {"name": "Sabun", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 250, "unit_cost": 1.5, "reorder_level": 60},
        {"name": "Kulak Çubuğu", "category": "Banyo Ürünleri", "unit": "paket", "quantity": 150, "unit_cost": 1.0, "reorder_level": 50},
        {"name": "Çarşaf Takımı", "category": "Yatak Ürünleri", "unit": "takım", "quantity": 60, "unit_cost": 45.0, "reorder_level": 20},
        {"name": "Havlu Seti", "category": "Banyo Ürünleri", "unit": "takım", "quantity": 80, "unit_cost": 35.0, "reorder_level": 25},
        {"name": "Yüz Havlusu", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 120, "unit_cost": 8.0, "reorder_level": 30},
        {"name": "El Havlusu", "category": "Banyo Ürünleri", "unit": "adet", "quantity": 120, "unit_cost": 6.0, "reorder_level": 30},
        {"name": "Bornoz", "category": "Oda Ürünleri", "unit": "adet", "quantity": 50, "unit_cost": 65.0, "reorder_level": 15},
        {"name": "Yastık", "category": "Yatak Ürünleri", "unit": "adet", "quantity": 100, "unit_cost": 25.0, "reorder_level": 30},
        {"name": "Battaniye", "category": "Yatak Ürünleri", "unit": "adet", "quantity": 60, "unit_cost": 55.0, "reorder_level": 20},
        {"name": "Yatak Örtüsü", "category": "Yatak Ürünleri", "unit": "adet", "quantity": 50, "unit_cost": 40.0, "reorder_level": 15},
        {"name": "Tuvalet Kağıdı", "category": "Temizlik", "unit": "rulo", "quantity": 300, "unit_cost": 2.0, "reorder_level": 100},
        {"name": "Kağıt Havlu", "category": "Temizlik", "unit": "rulo", "quantity": 200, "unit_cost": 3.0, "reorder_level": 60},
        {"name": "Çöp Poşeti", "category": "Temizlik", "unit": "adet", "quantity": 250, "unit_cost": 0.5, "reorder_level": 80},
        {"name": "Deterjan", "category": "Temizlik", "unit": "litre", "quantity": 50, "unit_cost": 15.0, "reorder_level": 15},
        {"name": "Cam Temizleyici", "category": "Temizlik", "unit": "litre", "quantity": 30, "unit_cost": 12.0, "reorder_level": 10},
    ]

    created_count = 0
    for amenity in amenities:
        # Check if already exists
        existing = await db.inventory_items.find_one({
            'tenant_id': current_user.tenant_id,
            'name': amenity['name']
        })

        if not existing:
            item = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                **amenity,
                'sku': f"HTL-{amenity['name'][:3].upper()}-{str(uuid.uuid4())[:8]}",
                'created_at': datetime.now(UTC).isoformat()
            }
            await db.inventory_items.insert_one(item)
            created_count += 1

    return {
        'message': f'Successfully seeded {created_count} hotel amenities',
        'total_items': len(amenities),
        'created': created_count
    }


@sub_router.get("/export/folio/{folio_id}")
@cached(ttl=600, key_prefix="export_folio")  # Cache for 10 min
async def export_folio_csv(
    folio_id: str,
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("export_data")),
):
    """Export folio transactions as CSV"""
    from core.security import _is_super_admin
    if not _is_super_admin(current_user) and not has_permission(current_user.role, Permission.EXPORT_DATA):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    import csv
    from io import StringIO

    # Get folio details
    folio_details = await get_folio_details(folio_id, current_user)
    folio = folio_details['folio']
    charges = folio_details['charges']
    payments = folio_details['payments']

    # Create CSV — Bug AN: charge descriptions / payment refs are user-controlled.
    from core.csv_safe import safe_writerow
    output = StringIO()
    writer = csv.writer(output)

    # Header
    safe_writerow(writer, [f"Folio Export - {folio['folio_number']}"])
    safe_writerow(writer, [f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])

    # Charges
    safe_writerow(writer, ['CHARGES'])
    safe_writerow(writer, ['Date', 'Category', 'Description', 'Quantity', 'Unit Price', 'Tax', 'Total', 'Voided'])
    for charge in charges:
        safe_writerow(writer, [
            charge['date'],
            charge['charge_category'],
            charge['description'],
            charge['quantity'],
            charge['unit_price'],
            charge['tax_amount'],
            charge['total'],
            'Yes' if charge.get('voided') else 'No'
        ])

    writer.writerow([])

    # Payments
    safe_writerow(writer, ['PAYMENTS'])
    safe_writerow(writer, ['Date', 'Method', 'Type', 'Amount', 'Reference'])
    for payment in payments:
        safe_writerow(writer, [
            payment['processed_at'],
            payment['method'],
            payment['payment_type'],
            payment['amount'],
            payment.get('reference', '')
        ])

    writer.writerow([])
    safe_writerow(writer, ['', '', '', 'Balance:', folio['balance']])

    csv_content = output.getvalue()
    output.close()

    return {
        'filename': f"folio_{folio['folio_number']}.csv",
        'content': csv_content,
        'content_type': 'text/csv'
    }



