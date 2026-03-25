"""
PMS / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.helpers import (
    require_module,
)
from core.security import (
    get_current_user,
    security,
)
from models.enums import CompanyStatus, UserRole
from models.schemas import Company, CompanyCreate, CreatePropertyRequest, User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Operations"])


# ── Inline Models ──

class PingTestRequest(BaseModel):
    target: str = "8.8.8.8"  # Google DNS
    count: int = 4


@router.get("/service/complaints")
async def get_complaints(
    status: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Şikayetleri listele"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    complaints = await db.service_complaints.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)

    return {'complaints': complaints, 'total': len(complaints)}


# ============= MULTI-PROPERTY MANAGEMENT =============



@router.post("/payments/intent")
async def payment_intent(payment_data: dict, current_user: User = Depends(get_current_user)):
    intent = {'id': str(uuid.uuid4()), 'amount': payment_data['amount'], 'status': 'pending'}
    await db.payment_intents.insert_one(intent)
    return {'success': True, 'intent_id': intent['id']}



@router.get("/payments/installment")
async def installment_calc(amount: float, months: int, current_user: User = Depends(get_current_user)):
    total = amount * (1 + months * 0.01)
    return {'monthly': round(total/months, 2), 'total': round(total, 2)}


@router.post("/payments/create-intent")
async def create_payment_intent(payment_data: dict, current_user: User = Depends(get_current_user)):
    intent = {
        'id': str(uuid.uuid4()), 'amount': payment_data['amount'],
        'status': 'pending', 'stripe_id': f'pi_mock_{str(uuid.uuid4())[:8]}'
    }
    await db.payment_intents.insert_one(intent)


# ============= GDS INTEGRATION (AMADEUS, SABRE, GALILEO) =============



@router.post("/gds/push-rate")
async def push_rate_to_gds(rate_data: dict, current_user: User = Depends(get_current_user)):
    """GDS'e rate ve availability gönder"""
    # Simulated GDS push (real: Amadeus/Sabre API)
    gds_update = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'gds_provider': rate_data.get('provider', 'Amadeus'),
        'room_type': rate_data['room_type'],
        'rate': rate_data['rate'],
        'availability': rate_data['availability'],
        'pushed_at': datetime.now(UTC).isoformat(),
        'success': True
    }
    await db.gds_rate_updates.insert_one(gds_update)
    return {'success': True, 'message': f'{gds_update["gds_provider"]} GDS güncellendi', 'update_id': gds_update['id']}



@router.get("/gds/reservations")
async def get_gds_reservations(current_user: User = Depends(get_current_user)):
    """GDS'ten gelen rezervasyonlar"""
    reservations = await db.gds_reservations.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    return {'reservations': reservations, 'total': len(reservations)}

# ============= MOBILE APP BACKEND =============



@router.post("/mobile/register-device")
async def register_mobile_device(device_data: dict, current_user: User = Depends(get_current_user)):
    """Mobil cihaz kaydı"""
    device = {
        'id': str(uuid.uuid4()),
        'user_id': current_user.id,
        'device_id': device_data['device_id'],
        'device_type': device_data['device_type'],
        'push_token': device_data.get('push_token'),
        'app_version': device_data.get('app_version', '1.0.0'),
        'os_version': device_data.get('os_version'),
        'registered_at': datetime.now(UTC).isoformat(),
        'last_active': datetime.now(UTC).isoformat()
    }
    await db.mobile_devices.insert_one(device)

    if device_data.get('push_token'):
        await db.push_device_tokens.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'user_id': current_user.id,
                'device_id': device_data['device_id']
            },
            {
                '$set': {
                    'tenant_id': current_user.tenant_id,
                    'user_id': current_user.id,
                    'device_id': device_data['device_id'],
                    'platform': device_data.get('device_type', 'mobile'),
                    'push_token': device_data['push_token'],
                    'app_version': device_data.get('app_version'),
                    'os_version': device_data.get('os_version'),
                    'subscriptions': DEFAULT_PUSH_CHANNELS,
                    'departments': [current_user.role] if current_user.role else [],
                    'updated_at': datetime.now(UTC).isoformat(),
                    'created_at': datetime.now(UTC).isoformat()
                }
            },
            upsert=True
        )
    return {'success': True, 'device_id': device['id']}



@router.post("/mobile/push-notification")
async def send_push_notification(notification_data: dict, current_user: User = Depends(get_current_user)):
    """Push notification gönder"""
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': notification_data['title'],
        'body': notification_data['body'],
        'sent_at': datetime.now(UTC).isoformat()
    }
    await db.push_notifications.insert_one(notification)
    return {'success': True, 'message': 'Push notification gönderildi (MOCK)'}


@router.post("/hr/staff")
async def add_staff_member(staff_data: dict, current_user: User = Depends(get_current_user)):
    """Yeni personel ekle"""
    staff = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': staff_data['name'],
        'email': staff_data['email'],
        'phone': staff_data['phone'],
        'department': staff_data['department'],
        'position': staff_data['position'],
        'hire_date': staff_data['hire_date'],
        'employment_type': staff_data.get('employment_type', 'full_time'),
        'performance_score': 0.0,
        'active': True,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.staff_members.insert_one(staff)
    return {'success': True, 'staff_id': staff['id']}



@router.get("/hr/staff")
async def get_staff_list(department: str | None = None, current_user: User = Depends(get_current_user)):
    """Personel listesi"""
    query = {'tenant_id': current_user.tenant_id, 'active': True}
    if department:
        query['department'] = department
    staff = await db.staff_members.find(query, {'_id': 0}).to_list(200)
    return {'staff': staff, 'total': len(staff)}



@router.post("/hr/shift")
async def create_shift(shift_data: dict, current_user: User = Depends(get_current_user)):
    """Vardiya oluştur"""
    shift = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': shift_data['staff_id'],
        'shift_date': shift_data['shift_date'],
        'shift_type': shift_data['shift_type'],
        'start_time': shift_data['start_time'],
        'end_time': shift_data['end_time'],
        'status': 'scheduled',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.shift_schedules.insert_one(shift)
    return {'success': True, 'shift_id': shift['id']}



@router.get("/hr/performance/{staff_id}")
async def get_staff_performance(staff_id: str, current_user: User = Depends(get_current_user)):
    """Personel performansı"""
    reviews = await db.performance_reviews.find({
        'staff_id': staff_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('reviewed_at', -1).to_list(10)

    avg_score = sum([r.get('overall_score', 0) for r in reviews]) / len(reviews) if reviews else 0

    return {
        'staff_id': staff_id,
        'recent_reviews': reviews,
        'avg_performance_score': round(avg_score, 2),
        'total_reviews': len(reviews)
    }


@router.get("/payments/installment-calculator")
async def installment_calculator(amount: float, installments: int, current_user: User = Depends(get_current_user)):
    rates = {1: 0.0, 2: 0.02, 3: 0.03, 6: 0.05, 9: 0.07, 12: 0.09}
    rate = rates.get(installments, 0.1)
    total = amount * (1 + rate)
    total / installments


@router.post("/companies", response_model=Company)
async def create_company(company_data: CompanyCreate, current_user: User = Depends(get_current_user)):
    """Create a new company. Status is 'pending' by default for quick-created companies from booking form."""
    company = Company(
        tenant_id=current_user.tenant_id,
        **company_data.model_dump()
    )
    company_dict = company.model_dump()
    company_dict['created_at'] = company_dict['created_at'].isoformat()
    company_dict['updated_at'] = company_dict['updated_at'].isoformat()
    await db.companies.insert_one(company_dict)
    return company



@router.get("/companies")
@cached(ttl=600, key_prefix="companies_list")  # Cache for 10 minutes
async def get_companies(
    search: str | None = None,
    status: CompanyStatus | None = None,
    limit: int = 1000,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get all companies with optional search, status filter, and pagination."""
    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status

    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'corporate_code': {'$regex': search, '$options': 'i'}}
        ]

    companies = await db.companies.find(query, {'_id': 0}).skip(offset).limit(limit).to_list(limit)
    # Remove response_model validation to allow flexible contracted_rate types
    return companies

# Alias for PMS module compatibility


@router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific company by ID."""
    company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company



@router.put("/companies/{company_id}", response_model=Company)
async def update_company(
    company_id: str,
    company_data: CompanyCreate,
    current_user: User = Depends(get_current_user)
):
    """Update company information. Used by sales team to complete pending company profiles."""
    company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    })

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = company_data.model_dump()
    update_data['updated_at'] = datetime.now(UTC).isoformat()

    await db.companies.update_one(
        {'id': company_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    updated_company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    return updated_company

# ============= FOLIO & BILLING ENGINE =============



@router.post("/payment/{payment_id}/void")
async def void_payment(
    payment_id: str,
    void_reason: str = "Voided by staff",
    current_user: User = Depends(get_current_user)
):
    """Void a payment"""
    payment = await db.payments.find_one({
        'id': payment_id,
        'tenant_id': current_user.tenant_id
    })

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.get('voided'):
        raise HTTPException(status_code=400, detail="Payment already voided")

    # Update payment
    await db.payments.update_one(
        {'id': payment_id},
        {'$set': {
            'voided': True,
            'voided_by': current_user.id,
            'voided_at': datetime.now(UTC).isoformat(),
            'void_reason': void_reason
        }}
    )

    # Recalculate folio balance
    folio_id = payment['folio_id']
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {'balance': balance}}
    )

    return {"message": "Payment voided successfully"}

# ── Folio by Booking ID (used by ReservationCalendar sidebar) ──

@router.get("/folio/booking/{booking_id}")
async def get_folios_by_booking(booking_id: str, current_user: User = Depends(get_current_user)):
    folios = await db.folios.find(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(20)
    return folios


# ============= GUEST MANAGEMENT =============

# ============= PMS - BOOKINGS MANAGEMENT =============



@router.get("/inventory/alerts")
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



@router.get("/inventory/consumption-report")
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



@router.post("/inventory/seed-hotel-amenities")
async def seed_hotel_amenities(current_user: User = Depends(get_current_user)):
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


@router.get("/export/folio/{folio_id}")
@cached(ttl=600, key_prefix="export_folio")  # Cache for 10 min
async def export_folio_csv(folio_id: str, current_user: User = Depends(get_current_user)):
    """Export folio transactions as CSV"""
    if not has_permission(current_user.role, Permission.EXPORT_DATA):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    import csv
    from io import StringIO

    # Get folio details
    folio_details = await get_folio_details(folio_id, current_user)
    folio = folio_details['folio']
    charges = folio_details['charges']
    payments = folio_details['payments']

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([f"Folio Export - {folio['folio_number']}"])
    writer.writerow([f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])

    # Charges
    writer.writerow(['CHARGES'])
    writer.writerow(['Date', 'Category', 'Description', 'Quantity', 'Unit Price', 'Tax', 'Total', 'Voided'])
    for charge in charges:
        writer.writerow([
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
    writer.writerow(['PAYMENTS'])
    writer.writerow(['Date', 'Method', 'Type', 'Amount', 'Reference'])
    for payment in payments:
        writer.writerow([
            payment['processed_at'],
            payment['method'],
            payment['payment_type'],
            payment['amount'],
            payment.get('reference', '')
        ])

    writer.writerow([])
    writer.writerow(['', '', '', 'Balance:', folio['balance']])

    csv_content = output.getvalue()
    output.close()

    return {
        'filename': f"folio_{folio['folio_number']}.csv",
        'content': csv_content,
        'content_type': 'text/csv'
    }



@router.post("/multi-property/properties")
async def create_property(
    request: CreatePropertyRequest,
    current_user: User = Depends(get_current_user)
):
    """Add new property to portfolio"""
    property_obj = {
        'id': str(uuid.uuid4()),
        'portfolio_id': current_user.tenant_id,
        'property_name': request.property_name,
        'property_code': request.property_code,
        'location': request.location,
        'total_rooms': request.total_rooms,
        'property_type': request.property_type,
        'status': request.status,
        'created_at': datetime.now(UTC).isoformat()
    }

    property_copy = property_obj.copy()
    await db.properties.insert_one(property_copy)
    return property_obj



@router.get("/multi-property/consolidated-report")
async def get_consolidated_report(
    start_date: str,
    end_date: str,
    metric: str = 'occupancy',
    current_user: User = Depends(get_current_user)
):
    """Get consolidated report across properties"""
    properties = await db.properties.find(
        {'portfolio_id': current_user.tenant_id, 'status': 'active'},
        {'_id': 0}
    ).to_list(100)

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    days = (end - start).days + 1

    report_data = []

    for day in range(days):
        current_date = (start + timedelta(days=day)).date().isoformat()

        day_data = {
            'date': current_date,
            'properties': []
        }

        for prop in properties:
            # Simplified metrics
            if metric == 'occupancy':
                rooms = await db.rooms.count_documents({'tenant_id': prop['id']})
                occupied = await db.rooms.count_documents({
                    'tenant_id': prop['id'],
                    'room_status': 'occupied'
                })
                value = (occupied / rooms * 100) if rooms > 0 else 0
            elif metric == 'revenue':
                pipeline = [
                    {
                        '$match': {
                            'tenant_id': prop['id'],
                            'charge_date': current_date,
                            'voided': False
                        }
                    },
                    {
                        '$group': {
                            '_id': None,
                            'total': {'$sum': '$total'}
                        }
                    }
                ]
                result = await db.folio_charges.aggregate(pipeline).to_list(1)
                value = result[0]['total'] if result else 0.0
            else:
                value = 0

            day_data['properties'].append({
                'property_id': prop['id'],
                'property_name': prop['property_name'],
                'value': round(value, 2)
            })

        report_data.append(day_data)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'metric': metric,
        'data': report_data
    }


@router.get("/mobile/staff/dashboard")
async def get_staff_mobile_dashboard(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms_mobile")),
):
    """
    Mobile staff dashboard
    - Role-based dashboard
    - Quick actions
    - Today's tasks
    """
    role = current_user.role

    dashboard = {
        'user_name': current_user.name,
        'user_role': role.value,
        'quick_actions': [],
        'today_tasks': [],
        'notifications_count': 0
    }

    if role == UserRole.HOUSEKEEPING:
        # Housekeeping tasks
        tasks = []
        async for task in db.housekeeping_tasks.find({
            'tenant_id': current_user.tenant_id,
            'assigned_to': current_user.name,
            'status': {'$in': ['pending', 'in_progress']}
        }).limit(20):
            room = await db.rooms.find_one({'id': task.get('room_id')})
            tasks.append({
                'task_id': task.get('id'),
                'room_number': room.get('room_number') if room else 'N/A',
                'task_type': task.get('task_type'),
                'priority': task.get('priority'),
                'status': task.get('status')
            })

        dashboard['quick_actions'] = ['Start Task', 'Report Issue', 'Take Photo']
        dashboard['today_tasks'] = tasks
        dashboard['notifications_count'] = len(tasks)

    elif role == UserRole.FRONT_DESK:
        # Check-in tasks
        today = datetime.now().date().isoformat()
        arrivals = []
        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': today,
            'status': {'$in': ['confirmed', 'guaranteed']}
        }).limit(10):
            guest = await db.guests.find_one({'id': booking.get('guest_id')})
            arrivals.append({
                'booking_id': booking.get('id'),
                'guest_name': guest.get('name') if guest else 'Guest',
                'room': booking.get('room_id'),
                'status': 'Pending Check-in'
            })

        dashboard['quick_actions'] = ['Quick Check-in', 'Walk-in Booking', 'Scan Passport']
        dashboard['today_tasks'] = arrivals
        dashboard['notifications_count'] = len(arrivals)

    elif role == UserRole.SUPERVISOR or role == UserRole.ADMIN:
        # Supervisor checklists
        dashboard['quick_actions'] = ['View Reports', 'Staff Performance', 'Occupancy Status']
        dashboard['today_tasks'] = [
            {'type': 'checklist', 'title': 'Morning Inspection', 'status': 'pending'},
            {'type': 'checklist', 'title': 'Revenue Review', 'status': 'pending'},
            {'type': 'checklist', 'title': 'Staff Briefing', 'status': 'completed'}
        ]

    return dashboard




@router.post("/mobile/staff/quick-checkin")
async def mobile_quick_checkin(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Quick check-in from mobile — atomic transaction."""
    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
    try:
        result = await check_in_booking_atomic(
            booking_id=booking_id,
            tenant_id=current_user.tenant_id,
            actor_id=current_user.id,
            actor_name=current_user.name,
        )
        return {
            'success': True,
            'message': 'Guest checked in successfully',
            'booking_id': booking_id,
            'checked_in_at': result.get('checked_in_at'),
        }
    except CheckInError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/properties/quick-list")
async def get_quick_property_list(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get quick property list for fast switching
    Returns only essential information for performance
    """
    current_user = await get_current_user(credentials)

    # Get all properties for this tenant
    properties = []
    async for prop in db.properties.find({'tenant_id': current_user.tenant_id}):
        properties.append({
            'id': prop.get('id', str(uuid.uuid4())),
            'property_id': prop.get('property_id', prop.get('id')),
            'name': prop.get('name', prop.get('property_name', 'Unnamed Property')),
            'location': prop.get('location', prop.get('city', 'Unknown')),
            'type': prop.get('type', prop.get('property_type', 'hotel')),
            'logo': prop.get('logo', ''),
            'is_active': prop.get('is_active', True),
            'room_count': prop.get('room_count', 0)
        })

    # If no properties in DB, return sample data
    if len(properties) == 0:
        properties = [
            {
                'id': str(uuid.uuid4()),
                'property_id': 'property_1',
                'name': 'Grand Hotel Istanbul',
                'location': 'İstanbul, Türkiye',
                'type': 'hotel',
                'logo': '',
                'is_active': True,
                'room_count': 120
            },
            {
                'id': str(uuid.uuid4()),
                'property_id': 'property_2',
                'name': 'Seaside Resort Antalya',
                'location': 'Antalya, Türkiye',
                'type': 'resort',
                'logo': '',
                'is_active': True,
                'room_count': 250
            },
            {
                'id': str(uuid.uuid4()),
                'property_id': 'property_3',
                'name': 'City Boutique Ankara',
                'location': 'Ankara, Türkiye',
                'type': 'boutique',
                'logo': '',
                'is_active': True,
                'room_count': 45
            }
        ]

    # Get user's current property
    current_property_id = current_user.property_id if hasattr(current_user, 'property_id') else None

    return {
        'properties': properties,
        'count': len(properties),
        'current_property_id': current_property_id
    }


# 2. PUT /api/user/switch-property/{property_id} - Switch active property


@router.put("/user/switch-property/{property_id}")
async def switch_property(
    property_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Switch user's active property
    Updates user's current property selection
    """
    current_user = await get_current_user(credentials)

    # Verify property exists and belongs to tenant
    property_doc = await db.properties.find_one({
        '$or': [
            {'id': property_id, 'tenant_id': current_user.tenant_id},
            {'property_id': property_id, 'tenant_id': current_user.tenant_id}
        ]
    })

    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found or access denied")

    # Update user's current property
    await db.users.update_one(
        {'id': current_user.id},
        {
            '$set': {
                'property_id': property_id,
                'current_property': property_doc.get('name', 'Unknown'),
                'last_property_switch': datetime.now(UTC).isoformat()
            }
        }
    )

    # Log the switch
    activity_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.id,
        'user_name': current_user.name,
        'action': 'property_switch',
        'property_id': property_id,
        'property_name': property_doc.get('name', 'Unknown'),
        'timestamp': datetime.now(UTC).isoformat()
    }
    await db.activity_logs.insert_one(activity_log)

    return {
        'message': 'Tesis başarıyla değiştirildi',
        'property_id': property_id,
        'property_name': property_doc.get('name', 'Unknown'),
        'switched_at': datetime.now(UTC).isoformat()
    }


@router.get("/analytics/7day-trend")
async def get_7day_trend(
    current_user: User = Depends(get_current_user)
):
    """
    Get 7-day trend for arrivals, departures, revenue, occupancy
    """
    try:
        today = datetime.now(UTC).date()
        trend_data = []

        for i in range(6, -1, -1):  # Last 7 days
            date = today - timedelta(days=i)
            date_str = date.isoformat()

            # Get arrivals for this date
            arrivals = await db.bookings.count_documents({
                'check_in': date_str,
                'tenant_id': current_user.tenant_id
            })

            # Get departures for this date
            departures = await db.bookings.count_documents({
                'check_out': date_str,
                'tenant_id': current_user.tenant_id
            })

            # Get occupancy (checked in bookings)
            occupancy = await db.bookings.count_documents({
                'check_in': {'$lte': date_str},
                'check_out': {'$gt': date_str},
                'status': 'checked_in',
                'tenant_id': current_user.tenant_id
            })

            # Calculate revenue for the day (simplified)
            daily_bookings = await db.bookings.find({
                'check_in': {'$lte': date_str},
                'check_out': {'$gt': date_str},
                'status': {'$in': ['checked_in', 'checked_out']},
                'tenant_id': current_user.tenant_id
            }, {'_id': 0, 'total_amount': 1}).to_list(500)

            daily_revenue = sum(b.get('total_amount', 0) for b in daily_bookings)

            trend_data.append({
                'date': date_str,
                'day_name': date.strftime('%a'),
                'arrivals': arrivals,
                'departures': departures,
                'occupancy': occupancy,
                'revenue': round(daily_revenue, 2)
            })

        # Calculate changes
        if len(trend_data) >= 2:
            latest = trend_data[-1]
            previous = trend_data[-2]

            changes = {
                'arrivals_change': latest['arrivals'] - previous['arrivals'],
                'departures_change': latest['departures'] - previous['departures'],
                'occupancy_change': latest['occupancy'] - previous['occupancy'],
                'revenue_change': round(latest['revenue'] - previous['revenue'], 2)
            }
        else:
            changes = {}

        return {
            'trend': trend_data,
            'changes': changes,
            'period': '7 days',
            'generated_at': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get 7-day trend: {str(e)}")


# ============================================================================
# SLA CONFIGURATION & TRACKING
# ============================================================================



@router.post("/network/ping")
async def network_ping_test(
    request: PingTestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Perform ping test to measure latency
    """
    try:
        import socket
        import time

        # Use TCP connection test instead of ICMP ping (which requires root)
        ping_times = []
        successful_pings = 0

        for i in range(request.count):
            try:
                start_time = time.time()

                # Try to connect to port 80 (HTTP) or 443 (HTTPS) for web connectivity test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)  # 3 second timeout

                # For IP addresses, use port 80. For domain names, try 80 first, then 443
                port = 80
                if not request.target.replace('.', '').isdigit():  # Not an IP address
                    try:
                        result = sock.connect_ex((request.target, 443))  # Try HTTPS first
                        if result != 0:
                            sock.close()
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(3)
                            port = 80
                    except Exception:
                        port = 80

                result = sock.connect_ex((request.target, port))
                end_time = time.time()

                if result == 0:
                    latency_ms = (end_time - start_time) * 1000
                    ping_times.append(latency_ms)
                    successful_pings += 1

                sock.close()

                # Small delay between pings
                if i < request.count - 1:
                    time.sleep(0.5)

            except Exception:
                # Connection failed for this attempt
                pass

        if ping_times:
            avg_latency = sum(ping_times) / len(ping_times)
            min_latency = min(ping_times)
            max_latency = max(ping_times)
            packet_loss = ((request.count - successful_pings) / request.count) * 100
        else:
            avg_latency = 0
            min_latency = 0
            max_latency = 0
            packet_loss = 100

        # Determine connection quality
        if avg_latency < 50:
            quality = 'excellent'
        elif avg_latency < 100:
            quality = 'good'
        elif avg_latency < 200:
            quality = 'fair'
        else:
            quality = 'poor'

        return {
            'target': request.target,
            'packets_sent': request.count,
            'packets_received': successful_pings,
            'packet_loss_percent': round(packet_loss, 2),
            'latency': {
                'average': round(avg_latency, 2),
                'min': round(min_latency, 2),
                'max': round(max_latency, 2)
            },
            'quality': quality
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ping failed: {str(e)}")

# ===== LANDING PAGE - DEMO REQUEST ENDPOINT =====


@router.get("/analytics/occupancy-trend")
async def get_occupancy_trend(
    days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get occupancy trend for the last N days"""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    # Get all bookings in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$ne': 'cancelled'},
        '$and': [
            {'check_out': {'$gt': start_date.isoformat()}},
            {'check_in': {'$lt': end_date.isoformat()}}
        ]
    }).to_list(length=10000)

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Calculate daily occupancy
    trend_data = []
    current = start_date

    while current <= end_date:
        # Count rooms occupied on this date
        occupied = 0
        for booking in bookings:
            check_in = datetime.fromisoformat(booking['check_in'].replace('Z', '+00:00'))
            check_out = datetime.fromisoformat(booking['check_out'].replace('Z', '+00:00'))

            if check_in.date() <= current.date() < check_out.date():
                occupied += 1

        occupancy_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0

        trend_data.append({
            'date': current.strftime('%Y-%m-%d'),
            'occupancy_rate': round(occupancy_rate, 2),
            'occupied_rooms': occupied,
            'total_rooms': total_rooms
        })

        current += timedelta(days=1)

    return {
        'success': True,
        'days': days,
        'trend': trend_data,
        'average_occupancy': round(sum(d['occupancy_rate'] for d in trend_data) / len(trend_data), 2) if trend_data else 0
    }




@router.get("/analytics/revenue-trend")
async def get_revenue_trend(
    days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue trend for the last N days"""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    # Get all folios in date range
    folios = await db.folios.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_date.isoformat(),
            '$lte': end_date.isoformat()
        }
    }).to_list(length=10000)

    # Calculate daily revenue
    trend_data = []
    current = start_date

    while current <= end_date:
        # Sum revenue for this date
        daily_revenue = 0
        for folio in folios:
            folio_date = datetime.fromisoformat(folio['created_at'].replace('Z', '+00:00'))
            if folio_date.date() == current.date():
                daily_revenue += folio.get('total_charges', 0)

        trend_data.append({
            'date': current.strftime('%Y-%m-%d'),
            'revenue': round(daily_revenue, 2)
        })

        current += timedelta(days=1)

    total_revenue = sum(d['revenue'] for d in trend_data)
    average_daily = round(total_revenue / len(trend_data), 2) if trend_data else 0

    return {
        'success': True,
        'days': days,
        'trend': trend_data,
        'total_revenue': round(total_revenue, 2),
        'average_daily_revenue': average_daily
    }



@router.get("/analytics/booking-trends")
async def get_booking_trends(
    days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get booking trends for the last N days"""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    # Get all bookings created in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_date.isoformat(),
            '$lte': end_date.isoformat()
        }
    }).to_list(length=10000)

    # Calculate daily booking counts
    trend_data = []
    current = start_date

    while current <= end_date:
        # Count bookings created on this date
        daily_bookings = 0
        for booking in bookings:
            booking_date = datetime.fromisoformat(booking['created_at'].replace('Z', '+00:00'))
            if booking_date.date() == current.date():
                daily_bookings += 1

        trend_data.append({
            'date': current.strftime('%Y-%m-%d'),
            'bookings': daily_bookings
        })

        current += timedelta(days=1)

    total_bookings = sum(d['bookings'] for d in trend_data)
    average_daily = round(total_bookings / len(trend_data), 2) if trend_data else 0

    return {
        'success': True,
        'days': days,
        'trend': trend_data,
        'total_bookings': total_bookings,
        'average_daily_bookings': average_daily
    }



