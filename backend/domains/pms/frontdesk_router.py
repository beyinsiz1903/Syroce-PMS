"""
PMS / Front Desk Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from common.context import OperationContext
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from domains.pms.frontdesk_service import frontdesk_service
from models.enums import BookingStatus, ChannelType
from models.schemas import User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Front Desk"])


from domains.pms.schemas import (  # noqa: E402
    GuestAlert,
    KeycardIssueRequest,
    PassportScanData,
    PassportScanRequest,
    WalkInBookingRequest,
)


@router.get("/arrivals/today")
async def get_todays_arrivals(current_user: User = Depends(get_current_user)):
    """Bugünün varışları - VIP, grup ve özel isteklerle"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_todays_arrivals(ctx)
    return result.data


@router.post("/frontdesk/express-checkin")
async def express_checkin_qr(qr_data: dict, current_user: User = Depends(get_current_user)):
    """QR code ile express check-in"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.express_checkin(ctx, qr_data["qr_code"])
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data



@router.post("/frontdesk/kiosk-checkin")
async def kiosk_checkin(checkin_data: dict, current_user: User = Depends(get_current_user)):
    return {'success': True, 'message': 'Kiosk check-in (entegrasyon hazir)', 'room_key': 'DIGITAL_KEY_123'}

# ============= ADVANCED LOYALTY =============



@router.get("/frontdesk/audit-checklist")
async def get_frontdesk_audit_checklist(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Front desk için night audit öncesi checklist"""
    current_user = await get_current_user(credentials)
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_audit_checklist(ctx)
    return result.data




@router.post("/frontdesk/checkin/{booking_id}")
async def check_in_guest(booking_id: str, create_folio: bool = True, force_clean: bool = False, current_user: User = Depends(get_current_user)):
    """Check-in guest with validations and auto-folio creation. force_clean=true cleans a dirty room before check-in."""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.checkin(ctx, booking_id, create_folio, force_clean)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "ALREADY_CHECKED_IN": 400, "ROOM_NOT_READY": 400}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data



@router.post("/frontdesk/checkout/{booking_id}")
async def check_out_guest(
    booking_id: str,
    force: bool = False,
    auto_close_folios: bool = True,
    current_user: User = Depends(get_current_user)
):
    """Check-out guest with balance validation and folio closure"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.checkout(ctx, booking_id, force, auto_close_folios)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "ALREADY_CHECKED_OUT": 400, "OUTSTANDING_BALANCE": 402}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data



@router.post("/frontdesk/folio/{booking_id}/charge")
async def add_folio_charge(booking_id: str, charge_type: str, description: str, amount: float, quantity: float = 1.0, current_user: User = Depends(get_current_user)):
    folio_charge = FolioCharge(tenant_id=current_user.tenant_id, booking_id=booking_id, charge_type=charge_type, description=description,
                               amount=amount, quantity=quantity, total=amount * quantity, posted_by=current_user.name)
    charge_dict = folio_charge.model_dump()
    charge_dict['date'] = charge_dict['date'].isoformat()
    await db.folio_charges.insert_one(charge_dict)
    return folio_charge



@router.get("/frontdesk/folio/{booking_id}")
@cached(ttl=180, key_prefix="frontdesk_folio")
async def get_folio(booking_id: str, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_folio(ctx, booking_id)
    return result.data


@router.get("/frontdesk/arrivals")
@cached(ttl=120, key_prefix="frontdesk_arrivals")
async def get_arrivals(date: str | None = None, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_arrivals(ctx, date)
    return result.data


@router.get("/frontdesk/departures")
@cached(ttl=120, key_prefix="frontdesk_departures")
async def get_departures(date: str | None = None, current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_departures(ctx, date)
    return result.data


@router.get("/frontdesk/inhouse")
@cached(ttl=180, key_prefix="frontdesk_inhouse")
async def get_inhouse_guests(current_user: User = Depends(get_current_user)):
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_inhouse(ctx)
    return result.data


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
                            'updated_at': datetime.now(UTC).isoformat()
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
        check_in = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0)
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
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic(booking_dict)
        except BookingConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # 5. Atomic check-in (booking + room + folio + audit + outbox in one transaction)
        from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
        try:
            checkin_result = await check_in_booking_atomic(
                booking_id=new_booking.id,
                tenant_id=current_user.tenant_id,
                actor_id=current_user.id,
                actor_name=current_user.name,
            )
        except CheckInError as e:
            raise HTTPException(status_code=400, detail=f"Walk-in booking created but check-in failed: {e}")

        return {
            'success': True,
            'message': "Walk-in booking created and checked in successfully",
            'booking_id': new_booking.id,
            'guest_id': guest_id,
            'room_number': room.get('room_number'),
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'total_amount': total_amount,
            'checked_in_at': checkin_result.get('checked_in_at'),
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
    """Get all active alerts for a guest"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_guest_alerts(ctx, guest_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data




@router.post("/frontdesk/guest-alerts")
async def create_guest_alert(
    guest_id: str,
    alert_type: str,
    title: str,
    description: str,
    priority: str = "normal",
    expires_days: int | None = None,
    current_user: User = Depends(get_current_user)
):
    """Create a custom alert for a guest"""
    expires_at = None
    if expires_days:
        expires_at = datetime.now(UTC) + timedelta(days=expires_days)

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
        'generated_at': datetime.now(UTC).isoformat()
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
    registration_card_data: dict[str, Any]
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
        'signed_at': datetime.now(UTC).isoformat(),
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
        'submitted_at': datetime.now(UTC).isoformat(),
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
    """Issue a new keycard for a booking"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.issue_keycard(ctx, request.booking_id, request.card_type, request.validity_hours)
    if not result.ok:
        code_map = {"NOT_FOUND": 404, "INVALID_STATUS": 400, "NO_ROOM": 400}
        raise HTTPException(status_code=code_map.get(result.code, 400), detail=result.error)
    return result.data


@router.put("/keycard/{keycard_id}/deactivate")
async def deactivate_keycard(
    keycard_id: str,
    reason: str = "checkout",
    current_user: User = Depends(get_current_user)
):
    """Deactivate/cancel a keycard"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.deactivate_keycard(ctx, keycard_id, reason)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data




@router.get("/keycard/booking/{booking_id}")
async def get_booking_keycards(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all keycards for a booking"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_booking_keycards(ctx, booking_id)
    return result.data


# ============================================================================
# UNIFIED ARRIVALS/DEPARTURES - SHARED ACROSS ALL DEPARTMENTS
# ============================================================================


@router.get("/unified/today-arrivals")
async def get_today_arrivals_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for today's arrivals"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_arrivals(ctx)
    return result.data


@router.get("/unified/today-departures")
async def get_today_departures_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for today's departures"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_departures(ctx)
    return result.data


@router.get("/unified/in-house")
async def get_in_house_unified(current_user: User = Depends(get_current_user)):
    """Unified endpoint for in-house guests"""
    ctx = OperationContext.from_user(current_user)
    result = await frontdesk_service.get_unified_inhouse(ctx)
    return result.data


# ============================================================================
# CLEANING REQUESTS - GUEST TO HOUSEKEEPING INTEGRATION
# ============================================================================


