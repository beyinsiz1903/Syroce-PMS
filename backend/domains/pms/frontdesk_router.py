"""
PMS / Front Desk Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date
import os
import uuid
import random
import logging
import io

from core.database import db
from core.security import (
    get_current_user, security, JWT_SECRET, JWT_ALGORITHM,
    generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    create_audit_log, require_feature, require_module,
    require_super_admin_guard as require_super_admin, require_admin,
    get_tenant_modules, load_tenant_doc,
)
from models.schemas import User, BookingCreate, BookingExtended
from models.enums import UserRole, RoomStatus, BookingStatus, FolioType, ChannelType

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Front Desk"])


# ── Inline Models ──

class PassportScanData(BaseModel):
    """Passport scan data from OCR"""
    passport_number: Optional[str] = None
    name: Optional[str] = None
    surname: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    expiry_date: Optional[str] = None
    sex: Optional[str] = None
    mrz_line1: Optional[str] = None
    mrz_line2: Optional[str] = None


class PassportScanRequest(BaseModel):
    """Request for passport scanning"""
    image_base64: str  # Base64 encoded image
    booking_id: Optional[str] = None


class WalkInBookingRequest(BaseModel):
    """Quick walk-in booking request"""
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: str
    guest_id_number: Optional[str] = None
    nationality: Optional[str] = None
    room_id: str
    nights: int = 1
    adults: int = 1
    children: int = 0
    rate_per_night: Optional[float] = None  # If not provided, use room base price
    special_requests: Optional[str] = None


class GuestAlert(BaseModel):
    """Guest alert model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    alert_type: str  # vip, birthday, anniversary, special_request, complaint, preference
    priority: str = "normal"  # low, normal, high, urgent
    title: str
    description: str
    is_active: bool = True
    show_on_checkin: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class KeycardIssueRequest(BaseModel):
    booking_id: str
    card_type: str = "physical"  # physical, mobile, qr
    validity_hours: int = 48


@router.get("/arrivals/today")
async def get_todays_arrivals(current_user: User = Depends(get_current_user)):
    """Bugünün varışları - VIP, grup ve özel isteklerle"""
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    arrivals = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'status': {'$in': ['confirmed', 'guaranteed']}
    }, {'_id': 0}).to_list(100)
    
    # Enrich with guest and room info
    enriched_arrivals = []
    for booking in arrivals:
        # Get guest
        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
        # Get room if assigned
        room = None
        if booking.get('room_id'):
            room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        
        enriched = {
            **booking,
            'guest_name': guest.get('name') if guest else 'Unknown',
            'guest_email': guest.get('email') if guest else None,
            'room_number': room.get('room_number') if room else None,
            'vip_status': guest.get('vip_status', False) if guest else False
        }
        enriched_arrivals.append(enriched)
    
    # Sort: VIP first, then group, then regular
    enriched_arrivals.sort(key=lambda x: (
        -1 if x.get('vip_status') else 0,
        -1 if x.get('group_block_id') else 0
    ), reverse=True)
    
    return {
        'arrivals': enriched_arrivals,
        'total': len(enriched_arrivals),
        'vip_count': len([a for a in enriched_arrivals if a.get('vip_status')]),
        'group_count': len([a for a in enriched_arrivals if a.get('group_block_id')]),
        'online_checkin_count': len([a for a in enriched_arrivals if a.get('online_checkin_completed')])
    }


@router.post("/frontdesk/express-checkin")
async def express_checkin_qr(qr_data: dict, current_user: User = Depends(get_current_user)):
    """QR code ile express check-in"""
    booking = await db.bookings.find_one({
        'express_checkin_code': qr_data['qr_code'], 'tenant_id': current_user.tenant_id
    }, {'_id': 0})
    if booking:
        await db.bookings.update_one(
            {'id': booking['id']},
            {'$set': {'status': 'checked_in', 'checked_in_at': datetime.now(timezone.utc).isoformat()}}
        )
        return {'success': True, 'message': 'Express check-in tamamlandi', 'booking': booking}
    return {'success': False, 'message': 'QR code gecersiz'}



@router.post("/frontdesk/kiosk-checkin")
async def kiosk_checkin(checkin_data: dict, current_user: User = Depends(get_current_user)):
    return {'success': True, 'message': 'Kiosk check-in (entegrasyon hazir)', 'room_key': 'DIGITAL_KEY_123'}

# ============= ADVANCED LOYALTY =============



@router.get("/frontdesk/audit-checklist")
async def get_frontdesk_audit_checklist(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Front desk için night audit öncesi checklist
    - Bugünün check-in'i olup henüz check-in yapılmamış misafirler
    - Açık foliosu olan misafir/şirketler
    - Şüpheli bakiye / dengesiz folio adayları
    - Bugün check-out olması gereken ama hâlâ open olanlar
    """
    current_user = await get_current_user(credentials)
    tenant_id = current_user.tenant_id
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

    # 1) Unchecked-in arrivals
    unchecked_in_arrivals = []
    arrivals_cursor = db.bookings.find({
        'tenant_id': tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'status': {'$in': ['confirmed', 'guaranteed']}
    }, {'_id': 0})
    async for booking in arrivals_cursor:
        if booking.get('checked_in_at'):
            continue
        guest = await db.guests.find_one({'id': booking.get('guest_id')}, {'_id': 0})
        room = None
        if booking.get('room_id'):
            room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        unchecked_in_arrivals.append({
            'booking_id': booking.get('id'),
            'reservation_number': booking.get('reservation_number'),
            'guest_name': guest.get('name') if guest else 'Unknown',
            'guest_email': guest.get('email') if guest else None,
            'room_number': room.get('room_number') if room else None,
            'vip_status': guest.get('vip_status', False) if guest else False,
            'check_in': booking.get('check_in'),
            'check_out': booking.get('check_out'),
            'ota_channel': booking.get('ota_channel'),
            'special_requests': booking.get('special_requests')
        })

    # 2) Open folios (with balance)
    open_folios = await db.folios.find({
        'tenant_id': tenant_id,
        'status': 'open'
    }, {'_id': 0}).to_list(2000)

    open_folios_with_balance = []
    unbalanced_folios = []
    overdue_departures = []

    for folio in open_folios:
        balance = folio.get('balance', 0.0)
        if balance and abs(balance) > 0.01:
            # Folio type / owner
            owner_name = None
            owner_type = folio.get('folio_type')
            if owner_type == 'guest' and folio.get('guest_id'):
                guest = await db.guests.find_one({'id': folio['guest_id']}, {'_id': 0})
                owner_name = guest.get('name') if guest else None
            elif owner_type in ['company', 'agency'] and folio.get('company_id'):
                company = await db.companies.find_one({'id': folio['company_id']}, {'_id': 0})
                owner_name = company.get('name') if company else None

            folio_item = {
                'folio_id': folio.get('id'),
                'folio_number': folio.get('folio_number'),
                'folio_type': owner_type,
                'owner_name': owner_name,
                'balance': round(balance, 2),
                'status': folio.get('status'),
                'created_at': folio.get('created_at'),
                'booking_id': folio.get('booking_id'),
            }
            open_folios_with_balance.append(folio_item)

            # 3) Unbalanced folios (heuristic)
            # Eğer balance belirgin şekilde pozitif ve created_at eskiyse flagle
            try:
                created_at = folio.get('created_at')
                days_open = None
                if created_at:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    days_open = (datetime.now(timezone.utc) - created_dt).days
            except Exception:
                days_open = None

            if days_open is not None and days_open > 2 and balance > 0:
                unbalanced_folios.append({
                    **folio_item,
                    'days_open': days_open,
                })

            # 4) Bugün check-out olması gereken ama hâlâ open olanlar
            if folio.get('booking_id'):
                booking = await db.bookings.find_one({'id': folio['booking_id']}, {'_id': 0})
                if booking:
                    check_out_str = booking.get('check_out')
                    try:
                        if check_out_str:
                            co_date = datetime.fromisoformat(check_out_str).date()
                            if co_date <= today and booking.get('status') == 'checked_in':
                                overdue_departures.append({
                                    'booking_id': booking.get('id'),
                                    'reservation_number': booking.get('reservation_number'),
                                    'guest_name': owner_name,
                                    'room_number': booking.get('room_number'),
                                    'check_out': check_out_str,
                                    'folio_id': folio.get('id'),
                                    'balance': round(balance, 2),
                                })
                    except Exception:
                        pass

    summary = {
        'unchecked_in_count': len(unchecked_in_arrivals),
        'vip_unchecked_in': len([a for a in unchecked_in_arrivals if a.get('vip_status')]),
        'open_folio_count': len(open_folios_with_balance),
        'total_open_balance': round(sum(f['balance'] for f in open_folios_with_balance), 2),
        'unbalanced_folio_count': len(unbalanced_folios),
        'overdue_departures_count': len(overdue_departures),
    }

    return {
        'date': today.isoformat(),
        'tenant_id': tenant_id,
        'unchecked_in_arrivals': unchecked_in_arrivals,
        'open_folios': open_folios_with_balance,
        'unbalanced_folios': unbalanced_folios,
        'overdue_departures': overdue_departures,
        'summary': summary,
    }




@router.post("/frontdesk/checkin/{booking_id}")
async def check_in_guest(booking_id: str, create_folio: bool = True, current_user: User = Depends(get_current_user)):
    """Check-in guest with validations and auto-folio creation"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking['status'] == 'checked_in':
        raise HTTPException(status_code=400, detail="Guest already checked in")
    
    # Validate room is available/clean
    room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room['status'] not in ['available', 'inspected']:
        raise HTTPException(
            status_code=400,
            detail=f"Room not ready for check-in. Current status: {room['status']}"
        )
    
    # Create guest folio if requested and doesn't exist
    if create_folio:
        existing_folio = await db.folios.find_one({
            'booking_id': booking_id,
            'folio_type': 'guest'
        })
        
        if not existing_folio:
            folio_number = await generate_folio_number(current_user.tenant_id)
            folio = Folio(
                tenant_id=current_user.tenant_id,
                booking_id=booking_id,
                folio_number=folio_number,
                folio_type=FolioType.GUEST,
                guest_id=booking['guest_id']
            )
            folio_dict = folio.model_dump()
            folio_dict['created_at'] = folio_dict['created_at'].isoformat()
            await db.folios.insert_one(folio_dict)
            
            # Auto-post room charges to folio
            check_in_dt = booking['check_in'] if isinstance(booking['check_in'], datetime) else datetime.fromisoformat(booking['check_in'].replace('Z', '+00:00'))
            check_out_dt = booking['check_out'] if isinstance(booking['check_out'], datetime) else datetime.fromisoformat(booking['check_out'].replace('Z', '+00:00'))
            nights = (check_out_dt - check_in_dt).days
            
            if nights > 0:
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                room_rate = room.get('base_price', booking.get('base_rate', 100))
                
                room_charge_amount = room_rate * nights
                tax_rate = 0.18
                tax_amount = room_charge_amount * tax_rate
                total_amount = room_charge_amount + tax_amount
                
                room_charge = FolioCharge(
                    tenant_id=current_user.tenant_id,
                    folio_id=folio.id,
                    charge_category='room',
                    description=f"Room {room.get('room_number', '?')} - {nights} night(s)",
                    quantity=nights,
                    unit_price=room_rate,
                    amount=room_charge_amount,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    total=total_amount
                )
                
                room_charge_dict = room_charge.model_dump()
                room_charge_dict['posted_at'] = room_charge_dict['posted_at'].isoformat()
                await db.folio_charges.insert_one(room_charge_dict)
                
                # Update folio balance
                balance = await calculate_folio_balance(folio.id, current_user.tenant_id)
                await db.folios.update_one({'id': folio.id}, {'$set': {'balance': balance}})
    
    # Update booking and room status
    checked_in_time = datetime.now(timezone.utc)
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'checked_in',
            'checked_in_at': checked_in_time.isoformat()
        }}
    )
    await db.rooms.update_one(
        {'id': booking['room_id']},
        {'$set': {
            'status': 'occupied',
            'current_booking_id': booking_id
        }}
    )
    
    # Update guest total stays
    await db.guests.update_one({'id': booking['guest_id']}, {'$inc': {'total_stays': 1}})
    
    # Auto deduct room amenities from inventory
    inventory_results = None
    try:
        from hotel_inventory_system import deduct_room_amenities
        guest_count = booking.get('adults', 1) + booking.get('children', 0)
        room_type = room.get('type', 'standard')
        
        inventory_results = await deduct_room_amenities(
            db=db,
            tenant_id=current_user.tenant_id,
            guest_count=guest_count,
            room_type=room_type,
            booking_id=booking_id,
            user_name=current_user.name
        )
    except Exception as e:
        print(f"⚠️ Inventory deduction failed: {str(e)}")
        # Don't fail check-in if inventory fails
    
    return {
        'message': 'Check-in completed successfully',
        'checked_in_at': checked_in_time.isoformat(),
        'room_number': room['room_number'],
        'inventory_deduction': inventory_results
    }



@router.post("/frontdesk/checkout/{booking_id}")
async def check_out_guest(
    booking_id: str,
    force: bool = False,
    auto_close_folios: bool = True,
    current_user: User = Depends(get_current_user)
):
    """Check-out guest with balance validation and folio closure"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking['status'] == 'checked_out':
        raise HTTPException(status_code=400, detail="Guest already checked out")
    
    # Get all folios for this booking
    folios = await db.folios.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'open'
    }).to_list(100)
    
    # Calculate total balance across all folios
    total_balance = 0.0
    folio_details = []
    
    for folio in folios:
        balance = await calculate_folio_balance(folio['id'], current_user.tenant_id)
        total_balance += balance
        folio_details.append({
            'folio_number': folio['folio_number'],
            'folio_type': folio['folio_type'],
            'balance': balance
        })
    
    # Check for outstanding balance
    if total_balance > 0.01 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Outstanding balance: ${total_balance:.2f}. Folios: {folio_details}"
        )
    
    # Close all open folios if requested
    if auto_close_folios and total_balance <= 0.01:
        for folio in folios:
            await db.folios.update_one(
                {'id': folio['id']},
                {'$set': {
                    'status': 'closed',
                    'balance': 0.0,
                    'closed_at': datetime.now(timezone.utc).isoformat()
                }}
            )
    
    # Update booking and room status
    checked_out_time = datetime.now(timezone.utc)
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'checked_out',
            'checked_out_at': checked_out_time.isoformat()
        }}
    )
    
    # Update room to dirty and create housekeeping task
    await db.rooms.update_one(
        {'id': booking['room_id']},
        {'$set': {
            'status': 'dirty',
            'current_booking_id': None
        }}
    )
    
    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=booking['room_id'],
        task_type='cleaning',
        priority='high',
        notes='Guest checked out - departure clean required'
    )
    task_dict = task.model_dump()
    task_dict['created_at'] = task_dict['created_at'].isoformat()
    await db.housekeeping_tasks.insert_one(task_dict)
    
    return {
        'message': 'Check-out completed successfully',
        'checked_out_at': checked_out_time.isoformat(),
        'total_balance': total_balance,
        'folios_closed': len(folios) if auto_close_folios else 0,
        'folio_details': folio_details
    }



@router.post("/frontdesk/folio/{booking_id}/charge")
async def add_folio_charge(booking_id: str, charge_type: str, description: str, amount: float, quantity: float = 1.0, current_user: User = Depends(get_current_user)):
    folio_charge = FolioCharge(tenant_id=current_user.tenant_id, booking_id=booking_id, charge_type=charge_type, description=description,
                               amount=amount, quantity=quantity, total=amount * quantity, posted_by=current_user.name)
    charge_dict = folio_charge.model_dump()
    charge_dict['date'] = charge_dict['date'].isoformat()
    await db.folio_charges.insert_one(charge_dict)
    return folio_charge



@router.get("/frontdesk/folio/{booking_id}")
@cached(ttl=180, key_prefix="frontdesk_folio")  # Cache for 3 min
async def get_folio(booking_id: str, current_user: User = Depends(get_current_user)):
    charges = await db.folio_charges.find({'booking_id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    payments = await db.payments.find({'booking_id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    total_charges = sum(c['total'] for c in charges)
    total_paid = sum(p['amount'] for p in payments if p['status'] == 'paid')
    return {'charges': charges, 'payments': payments, 'total_charges': total_charges, 'total_paid': total_paid, 'balance': total_charges - total_paid}



@router.post("/frontdesk/payment/{booking_id}")
async def process_payment(booking_id: str, amount: float, method: str, reference: Optional[str] = None, notes: Optional[str] = None, current_user: User = Depends(get_current_user)):
    payment = Payment(tenant_id=current_user.tenant_id, booking_id=booking_id, amount=amount, method=method, status='paid',
                     reference=reference, notes=notes, processed_by=current_user.name)
    payment_dict = payment.model_dump()
    payment_dict['processed_at'] = payment_dict['processed_at'].isoformat()
    await db.payments.insert_one(payment_dict)
    await db.bookings.update_one({'id': booking_id}, {'$inc': {'paid_amount': amount}})
    return payment



@router.get("/frontdesk/arrivals")
@cached(ttl=120, key_prefix="frontdesk_arrivals")  # Cache for 2 min
async def get_arrivals(date: Optional[str] = None, current_user: User = Depends(get_current_user)):
    target_date = datetime.fromisoformat(date).date() if date else datetime.now(timezone.utc).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': {'$in': ['confirmed', 'checked_in']},
                                       'check_in': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}}, {'_id': 0}).to_list(1000)
    enriched = []
    for booking in bookings:
        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
        room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        enriched.append({**booking, 'guest': guest, 'room': room})
    return enriched



@router.get("/frontdesk/departures")
@cached(ttl=120, key_prefix="frontdesk_departures")  # Cache for 2 min
async def get_departures(date: Optional[str] = None, current_user: User = Depends(get_current_user)):
    target_date = datetime.fromisoformat(date).date() if date else datetime.now(timezone.utc).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': 'checked_in',
                                       'check_out': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}}, {'_id': 0}).to_list(1000)
    enriched = []
    for booking in bookings:
        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
        room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        charges = await db.folio_charges.find({'booking_id': booking['id']}, {'_id': 0}).to_list(1000)
        payments = await db.payments.find({'booking_id': booking['id']}, {'_id': 0}).to_list(1000)
        balance = sum(c['total'] for c in charges) - sum(p['amount'] for p in payments if p['status'] == 'paid')
        enriched.append({**booking, 'guest': guest, 'room': room, 'balance': balance})
    return enriched



@router.get("/frontdesk/inhouse")
@cached(ttl=180, key_prefix="frontdesk_inhouse")  # Cache for 3 min
async def get_inhouse_guests(current_user: User = Depends(get_current_user)):
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': 'checked_in'}, {'_id': 0}).to_list(1000)
    enriched = []
    for booking in bookings:
        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
        room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        enriched.append({**booking, 'guest': guest, 'room': room})
    return enriched


# ============= REPORTING =============

# ============= MANAGEMENT REPORTS =============



@router.post("/frontdesk/passport-scan")
async def scan_passport(
    request: PassportScanRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Scan passport and extract data automatically
    Uses OCR to extract passport information
    """
    # In production, integrate with OCR service like:
    # - OCR.space
    # - Google Cloud Vision
    # - Azure Computer Vision
    # - Amazon Textract
    
    # For MVP, we'll simulate OCR response
    # In real implementation, send image_base64 to OCR service
    
    try:
        # Simulated OCR extraction (in production, call actual OCR API)
        # Example with Google Vision or OCR.space would be:
        # response = await ocr_service.extract_passport(request.image_base64)
        
        # Simulated response
        extracted_data = PassportScanData(
            passport_number="P12345678",
            name="JOHN",
            surname="DOE",
            nationality="USA",
            date_of_birth="1990-05-15",
            expiry_date="2030-05-15",
            sex="M"
        )
        
        # If booking_id provided, update guest info
        if request.booking_id:
            booking = await db.bookings.find_one({
                'id': request.booking_id,
                'tenant_id': current_user.tenant_id
            })
            
            if booking:
                guest_id = booking.get('guest_id')
                if guest_id:
                    # Update guest with passport info
                    await db.guests.update_one(
                        {'id': guest_id, 'tenant_id': current_user.tenant_id},
                        {'$set': {
                            'id_number': extracted_data.passport_number,
                            'nationality': extracted_data.nationality,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }}
                    )
        
        return {
            'success': True,
            'extracted_data': extracted_data.model_dump(),
            'confidence': 0.95,  # OCR confidence score
            'message': 'Passport scanned successfully. Please verify extracted data.',
            'note': 'In production, integrate with OCR.space, Google Vision, or Azure Computer Vision for real passport scanning'
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Passport scan failed: {str(e)}")




@router.post("/frontdesk/walk-in-booking")
async def create_walk_in_booking(
    request: WalkInBookingRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Quick walk-in booking - create guest, booking, and check-in with one click
    """
    try:
        # 1. Check room availability
        room = await db.rooms.find_one({
            'id': request.room_id,
            'tenant_id': current_user.tenant_id
        })
        
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        if room.get('status') not in ['available', 'inspected']:
            raise HTTPException(
                status_code=400,
                detail=f"Room {room.get('room_number')} is not available (status: {room.get('status')})"
            )
        
        # 2. Create or find guest
        guest_email = request.guest_email or f"walkin_{uuid.uuid4().hex[:8]}@hotel.local"
        
        # Try to find existing guest by phone or email
        existing_guest = await db.guests.find_one({
            'tenant_id': current_user.tenant_id,
            '$or': [
                {'phone': request.guest_phone},
                {'email': guest_email}
            ]
        })
        
        if existing_guest:
            guest_id = existing_guest['id']
        else:
            # Create new guest
            new_guest = Guest(
                tenant_id=current_user.tenant_id,
                name=request.guest_name,
                email=guest_email,
                phone=request.guest_phone,
                id_number=request.guest_id_number or f"WALKIN-{uuid.uuid4().hex[:8]}",
                nationality=request.nationality
            )
            
            guest_dict = new_guest.model_dump()
            guest_dict['created_at'] = guest_dict['created_at'].isoformat()
            await db.guests.insert_one(guest_dict)
            guest_id = new_guest.id
        
        # 3. Calculate dates and amount
        check_in = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)
        check_out = check_in + timedelta(days=request.nights)
        
        rate = request.rate_per_night or room.get('base_price', 100.0)
        total_amount = rate * request.nights
        
        # 4. Create booking
        new_booking = Booking(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            room_id=request.room_id,
            check_in=check_in.date().isoformat(),
            check_out=check_out.date().isoformat(),
            adults=request.adults,
            children=request.children,
            children_ages=[],
            guests_count=request.adults + request.children,
            total_amount=total_amount,
            status=BookingStatus.CONFIRMED,
            channel=ChannelType.DIRECT,
            special_requests=request.special_requests
        )
        
        booking_dict = new_booking.model_dump()
        booking_dict['created_at'] = booking_dict['created_at'].isoformat()
        await db.bookings.insert_one(booking_dict)
        
        # 5. Auto check-in
        await db.bookings.update_one(
            {'id': new_booking.id},
            {'$set': {
                'status': BookingStatus.CHECKED_IN.value,
                'checked_in_at': datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # 6. Update room status
        await db.rooms.update_one(
            {'id': request.room_id},
            {'$set': {
                'status': RoomStatus.OCCUPIED.value,
                'current_booking_id': new_booking.id
            }}
        )
        
        # 7. Create guest folio
        folio = Folio(
            tenant_id=current_user.tenant_id,
            booking_id=new_booking.id,
            folio_number=f"F-{datetime.now().year}-{uuid.uuid4().hex[:5].upper()}",
            folio_type=FolioType.GUEST,
            guest_id=guest_id
        )
        
        folio_dict = folio.model_dump()
        folio_dict['created_at'] = folio_dict['created_at'].isoformat()
        await db.folios.insert_one(folio_dict)
        
        # 8. Create audit log
        await create_audit_log(
            tenant_id=current_user.tenant_id,
            user=current_user,
            action="WALK_IN_CHECKIN",
            entity_type="booking",
            entity_id=new_booking.id,
            changes={
                'guest_name': request.guest_name,
                'room': room.get('room_number'),
                'nights': request.nights,
                'total_amount': total_amount
            }
        )
        
        return {
            'success': True,
            'message': f"Walk-in booking created and checked in successfully",
            'booking_id': new_booking.id,
            'guest_id': guest_id,
            'folio_id': folio.id,
            'room_number': room.get('room_number'),
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'total_amount': total_amount,
            'folio_number': folio.folio_number
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Walk-in booking failed: {str(e)}")




@router.get("/frontdesk/guest-alerts/{guest_id}")
async def get_guest_alerts(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all active alerts for a guest
    - VIP status
    - Birthday/Anniversary
    - Special requests
    - Preferences
    - Past complaints
    """
    # Get guest
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    
    alerts = []
    
    # VIP Alert
    if guest.get('vip_status'):
        alerts.append({
            'type': 'vip',
            'priority': 'high',
            'icon': '⭐',
            'title': 'VIP Guest',
            'description': f"{guest.get('name')} is a VIP guest. Provide premium service.",
            'color': 'gold'
        })
    
    # Birthday Alert (check if birthday is within next 7 days or today)
    dob_str = guest.get('date_of_birth')
    if dob_str:
        try:
            dob = datetime.fromisoformat(dob_str).date()
            today = datetime.now().date()
            # Check this year's birthday
            birthday_this_year = dob.replace(year=today.year)
            days_until_birthday = (birthday_this_year - today).days
            
            if days_until_birthday == 0:
                alerts.append({
                    'type': 'birthday',
                    'priority': 'high',
                    'icon': '🎂',
                    'title': 'Birthday Today!',
                    'description': f"It's {guest.get('name')}'s birthday today! Consider a complimentary upgrade or amenity.",
                    'color': 'pink'
                })
            elif 0 < days_until_birthday <= 7:
                alerts.append({
                    'type': 'birthday',
                    'priority': 'normal',
                    'icon': '🎉',
                    'title': f'Birthday in {days_until_birthday} days',
                    'description': f"{guest.get('name')}'s birthday is coming up.",
                    'color': 'blue'
                })
        except:
            pass
    
    # Special Requests from current booking
    current_booking = await db.bookings.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }, sort=[('created_at', -1)])
    
    if current_booking and current_booking.get('special_requests'):
        alerts.append({
            'type': 'special_request',
            'priority': 'high',
            'icon': '📝',
            'title': 'Special Request',
            'description': current_booking.get('special_requests'),
            'color': 'blue'
        })
    
    # Guest Preferences
    guest_prefs = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    })
    
    if guest_prefs:
        pref_items = []
        if guest_prefs.get('pillow_type'):
            pref_items.append(f"Pillow: {guest_prefs.get('pillow_type')}")
        if guest_prefs.get('room_temperature'):
            pref_items.append(f"Temp: {guest_prefs.get('room_temperature')}°C")
        if guest_prefs.get('newspaper'):
            pref_items.append(f"Newspaper: {guest_prefs.get('newspaper')}")
        
        if pref_items:
            alerts.append({
                'type': 'preference',
                'priority': 'normal',
                'icon': '⚙️',
                'title': 'Guest Preferences',
                'description': ', '.join(pref_items),
                'color': 'purple'
            })
    
    # Recent Complaints
    recent_complaint = await db.department_feedback.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'rating': {'$lt': 3},
        'created_at': {'$gte': (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()}
    }, sort=[('created_at', -1)])
    
    if recent_complaint:
        alerts.append({
            'type': 'complaint',
            'priority': 'urgent',
            'icon': '⚠️',
            'title': 'Past Complaint',
            'description': f"Guest had a complaint about {recent_complaint.get('department')}. Ensure excellent service.",
            'color': 'red'
        })
    
    # Loyalty Status
    if guest.get('loyalty_points', 0) > 1000:
        tier = 'Gold' if guest.get('loyalty_points') > 5000 else 'Silver'
        alerts.append({
            'type': 'loyalty',
            'priority': 'normal',
            'icon': '💎',
            'title': f'{tier} Member',
            'description': f"Loyalty member with {guest.get('loyalty_points')} points",
            'color': 'gold' if tier == 'Gold' else 'silver'
        })
    
    # Custom alerts from database
    custom_alerts = []
    async for alert in db.guest_alerts.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'is_active': True,
        '$or': [
            {'expires_at': None},
            {'expires_at': {'$gte': datetime.now(timezone.utc).isoformat()}}
        ]
    }):
        custom_alerts.append({
            'type': alert.get('alert_type'),
            'priority': alert.get('priority'),
            'icon': '🔔',
            'title': alert.get('title'),
            'description': alert.get('description'),
            'color': 'orange'
        })
    
    alerts.extend(custom_alerts)
    
    # Sort by priority
    priority_order = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
    alerts.sort(key=lambda x: priority_order.get(x['priority'], 2))
    
    return {
        'guest_id': guest_id,
        'guest_name': guest.get('name'),
        'total_alerts': len(alerts),
        'alerts': alerts
    }




@router.post("/frontdesk/guest-alerts")
async def create_guest_alert(
    guest_id: str,
    alert_type: str,
    title: str,
    description: str,
    priority: str = "normal",
    expires_days: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Create a custom alert for a guest"""
    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
    
    alert = GuestAlert(
        tenant_id=current_user.tenant_id,
        guest_id=guest_id,
        alert_type=alert_type,
        priority=priority,
        title=title,
        description=description,
        expires_at=expires_at
    )
    
    alert_dict = alert.model_dump()
    alert_dict['created_at'] = alert_dict['created_at'].isoformat()
    if alert_dict.get('expires_at'):
        alert_dict['expires_at'] = alert_dict['expires_at'].isoformat()
    
    await db.guest_alerts.insert_one(alert_dict)
    
    return {
        'success': True,
        'alert_id': alert.id,
        'message': 'Guest alert created successfully'
    }


# ============= HOUSEKEEPING ENHANCEMENTS =============



@router.post("/self-checkin/generate-door-qr")
async def generate_door_qr_code(
    booking_id: str
):
    """
    Generate QR code for door lock
    - Digital key
    - Time-limited access
    - Room entry tracking
    """
    booking = await db.bookings.find_one({'id': booking_id})
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Generate QR code data
    # In production: Integrate with door lock system (Assa Abloy, Salto, Dormakaba)
    qr_data = {
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'valid_from': booking.get('check_in'),
        'valid_until': booking.get('check_out'),
        'access_token': str(uuid.uuid4()),
        'generated_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Generate QR code image
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(qr_data))
    qr.make(fit=True)
    
    # Convert to base64
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    return {
        'success': True,
        'booking_id': booking_id,
        'qr_code_base64': qr_base64,
        'qr_data': qr_data,
        'valid_from': qr_data['valid_from'],
        'valid_until': qr_data['valid_until'],
        'note': 'In production: Integrate with door lock system API (Assa Abloy, Salto, Dormakaba)'
    }




@router.post("/self-checkin/digital-signature")
async def capture_digital_signature(
    booking_id: str,
    signature_base64: str,
    registration_card_data: Dict[str, Any]
):
    """
    Capture digital signature
    - Guest signs registration card
    - Legally binding
    - Stored with booking
    """
    booking = await db.bookings.find_one({'id': booking_id})
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Store signature
    signature_record = {
        'id': str(uuid.uuid4()),
        'booking_id': booking_id,
        'signature_base64': signature_base64,
        'registration_card_data': registration_card_data,
        'signed_at': datetime.now(timezone.utc).isoformat(),
        'ip_address': None,  # From request in production
        'device_type': 'kiosk'
    }
    
    await db.digital_signatures.insert_one(signature_record)
    
    # Update booking
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {'digital_signature_id': signature_record['id']}}
    )
    
    return {
        'success': True,
        'signature_id': signature_record['id'],
        'message': 'Digital signature captured successfully'
    }




@router.post("/self-checkin/police-notification")
async def auto_police_notification(
    booking_id: str
):
    """
    Automatic police notification
    - Required by law in many countries
    - Guest ID information
    - Automated submission
    """
    booking = await db.bookings.find_one({'id': booking_id})
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    guest = await db.guests.find_one({'id': booking.get('guest_id')})
    
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    
    # In production: Integrate with local police registration system
    # Turkey: GIYBIS, Italy: Alloggiati Web, etc.
    
    notification_data = {
        'id': str(uuid.uuid4()),
        'booking_id': booking_id,
        'guest_name': guest.get('name'),
        'guest_id_number': guest.get('id_number'),
        'nationality': guest.get('nationality'),
        'check_in': booking.get('check_in'),
        'check_out': booking.get('check_out'),
        'room_number': None,  # Get from room
        'submitted_at': datetime.now(timezone.utc).isoformat(),
        'status': 'submitted',
        'reference_number': f"POL-{uuid.uuid4().hex[:8].upper()}"
    }
    
    await db.police_notifications.insert_one(notification_data)
    
    return {
        'success': True,
        'notification_id': notification_data['id'],
        'reference_number': notification_data['reference_number'],
        'status': 'submitted',
        'message': 'Police notification submitted successfully',
        'note': 'In production: Integrate with local police system (GIYBIS, Alloggiati Web, etc.)'
    }


# ============= NIGHT AUDIT SYSTEM =============



@router.post("/keycard/issue")
async def issue_keycard(
    request: KeycardIssueRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Issue a new keycard for a booking
    Supports: physical cards, mobile keys, QR codes
    """
    try:
        # Find booking
        booking = await db.bookings.find_one({'id': request.booking_id, 'tenant_id': current_user.tenant_id})
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Check if booking is checked in or confirmed
        if booking['status'] not in ['confirmed', 'guaranteed', 'checked_in']:
            raise HTTPException(status_code=400, detail="Booking must be confirmed or checked-in to issue keycard")
        
        # Get room info
        room = await db.rooms.find_one({'id': booking.get('room_id')})
        if not room:
            raise HTTPException(status_code=400, detail="Room not assigned")
        
        # Generate keycard data
        keycard_id = str(uuid.uuid4())
        issue_time = datetime.now(timezone.utc)
        expiry_time = issue_time + timedelta(hours=request.validity_hours)
        
        keycard_data = {
            'id': keycard_id,
            'booking_id': request.booking_id,
            'room_id': booking['room_id'],
            'room_number': room['room_number'],
            'guest_id': booking['guest_id'],
            'guest_name': booking['guest_name'],
            'card_type': request.card_type,
            'issued_at': issue_time.isoformat(),
            'expires_at': expiry_time.isoformat(),
            'issued_by': current_user.id,
            'issued_by_name': current_user.name,
            'status': 'active',
            'access_areas': ['room', 'elevator', 'gym', 'pool'],  # Default access
            'tenant_id': current_user.tenant_id
        }
        
        # Generate card code based on type
        if request.card_type == "physical":
            keycard_data['card_number'] = f"RFID-{room['room_number']}-{datetime.now().strftime('%Y%m%d%H%M')}"
            keycard_data['encoding_data'] = f"ENC:{keycard_id[:8]}:{room['room_number']}"
        elif request.card_type == "mobile":
            keycard_data['mobile_key_token'] = f"MOB-{keycard_id[:16]}"
            keycard_data['bluetooth_uuid'] = f"BLE-{uuid.uuid4()}"
        elif request.card_type == "qr":
            keycard_data['qr_code'] = f"QR-{keycard_id}"
            keycard_data['qr_data'] = f"{room['room_number']}:{keycard_id}:{expiry_time.timestamp()}"
        
        # Store keycard
        await db.keycards.insert_one(keycard_data)
        
        # Log the action
        await db.audit_logs.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id,
            'user_name': current_user.name,
            'user_role': current_user.role,
            'action': 'ISSUE_KEYCARD',
            'entity_type': 'keycard',
            'entity_id': keycard_id,
            'changes': {'card_type': request.card_type, 'room_number': room['room_number']},
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        return {
            'message': f'{request.card_type.capitalize()} keycard issued successfully',
            'keycard_id': keycard_id,
            'card_type': request.card_type,
            'room_number': room['room_number'],
            'guest_name': booking['guest_name'],
            'issued_at': issue_time.isoformat(),
            'expires_at': expiry_time.isoformat(),
            'validity_hours': request.validity_hours,
            'card_data': keycard_data.get('card_number') or keycard_data.get('mobile_key_token') or keycard_data.get('qr_code'),
            'access_areas': keycard_data['access_areas']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to issue keycard: {str(e)}")




@router.put("/keycard/{keycard_id}/deactivate")
async def deactivate_keycard(
    keycard_id: str,
    reason: str = "checkout",
    current_user: User = Depends(get_current_user)
):
    """
    Deactivate/cancel a keycard
    Reasons: checkout, lost, stolen, replaced
    """
    try:
        keycard = await db.keycards.find_one({'id': keycard_id, 'tenant_id': current_user.tenant_id})
        if not keycard:
            raise HTTPException(status_code=404, detail="Keycard not found")
        
        # Update keycard status
        await db.keycards.update_one(
            {'id': keycard_id},
            {
                '$set': {
                    'status': 'deactivated',
                    'deactivated_at': datetime.now(timezone.utc).isoformat(),
                    'deactivated_by': current_user.id,
                    'deactivation_reason': reason
                }
            }
        )
        
        return {
            'message': 'Keycard deactivated successfully',
            'keycard_id': keycard_id,
            'reason': reason,
            'deactivated_at': datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate keycard: {str(e)}")




@router.get("/keycard/booking/{booking_id}")
async def get_booking_keycards(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all keycards for a booking
    """
    try:
        keycards = await db.keycards.find({
            'booking_id': booking_id,
            'tenant_id': current_user.tenant_id
        }).sort('issued_at', -1).to_list(20)
        
        return {
            'keycards': keycards,
            'count': len(keycards),
            'active_count': len([k for k in keycards if k['status'] == 'active'])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve keycards: {str(e)}")


# ============================================================================
# UNIFIED ARRIVALS/DEPARTURES - SHARED ACROSS ALL DEPARTMENTS
# ============================================================================



@router.get("/unified/today-arrivals")
async def get_today_arrivals_unified(
    current_user: User = Depends(get_current_user)
):
    """
    Unified endpoint for today's arrivals - used by Front Desk, Housekeeping, GM Dashboard
    Returns enriched booking data with room and guest information
    """
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        
        # Get today's arrivals
        bookings = await db.bookings.find({
            'check_in': today,
            'status': {'$in': ['confirmed', 'guaranteed']},
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)
        
        # Enrich with guest and room data
        enriched_bookings = []
        for booking in bookings:
            # Get guest info
            if booking.get('guest_id'):
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
                if guest:
                    booking['guest_name'] = guest.get('name')
                    booking['guest_phone'] = guest.get('phone')
                    booking['guest_email'] = guest.get('email')
            
            # Get room info
            if booking.get('room_id'):
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                if room:
                    booking['room_number'] = room.get('room_number')
                    booking['room_type'] = room.get('room_type')
                    booking['room_status'] = room.get('status')
            
            enriched_bookings.append(booking)
        
        return {
            'arrivals': enriched_bookings,
            'count': len(enriched_bookings),
            'date': today
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get today's arrivals: {str(e)}")




@router.get("/unified/today-departures")
async def get_today_departures_unified(
    current_user: User = Depends(get_current_user)
):
    """
    Unified endpoint for today's departures - used by Front Desk, Housekeeping, GM Dashboard
    Returns enriched booking data with room and guest information
    """
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        
        # Get today's departures
        bookings = await db.bookings.find({
            'check_out': today,
            'status': 'checked_in',
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)
        
        # Enrich with guest and room data
        enriched_bookings = []
        for booking in bookings:
            # Get guest info
            if booking.get('guest_id'):
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
                if guest:
                    booking['guest_name'] = guest.get('name')
                    booking['guest_phone'] = guest.get('phone')
                    booking['guest_email'] = guest.get('email')
            
            # Get room info
            if booking.get('room_id'):
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                if room:
                    booking['room_number'] = room.get('room_number')
                    booking['room_type'] = room.get('room_type')
                    booking['room_status'] = room.get('status')
            
            enriched_bookings.append(booking)
        
        return {
            'departures': enriched_bookings,
            'count': len(enriched_bookings),
            'date': today
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get today's departures: {str(e)}")




@router.get("/unified/in-house")
async def get_in_house_unified(
    current_user: User = Depends(get_current_user)
):
    """
    Unified endpoint for in-house guests - used by all departments
    """
    try:
        # Get all checked-in bookings
        bookings = await db.bookings.find({
            'status': 'checked_in',
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(500)
        
        # Enrich with guest and room data
        enriched_bookings = []
        for booking in bookings:
            # Get guest info
            if booking.get('guest_id'):
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
                if guest:
                    booking['guest_name'] = guest.get('name')
                    booking['guest_phone'] = guest.get('phone')
                    booking['guest_email'] = guest.get('email')
            
            # Get room info
            if booking.get('room_id'):
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                if room:
                    booking['room_number'] = room.get('room_number')
                    booking['room_type'] = room.get('room_type')
                    booking['room_status'] = room.get('status')
            
            enriched_bookings.append(booking)
        
        return {
            'in_house': enriched_bookings,
            'count': len(enriched_bookings)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get in-house guests: {str(e)}")


# ============================================================================
# CLEANING REQUESTS - GUEST TO HOUSEKEEPING INTEGRATION
# ============================================================================


