"""
PMS / Groups Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging

from core.database import db
from core.security import (
    get_current_user,
)
from models.schemas import User, CreateGroupReservationRequest, AssignGroupRoomsRequest, CreateBlockReservationRequest, UseBlockRoomRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["PMS / Groups"])

@router.post("/groups/create-block")
async def create_group_block(
    block_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Grup bloğu oluştur"""
    
    # Flexible field mapping
    group_name = block_data.get('group_name') or block_data.get('block_name')
    organization = block_data.get('organization') or block_data.get('group_type', '')
    contact_name = block_data.get('contact_name') or block_data.get('contact_person')
    contact_email = block_data.get('contact_email') or block_data.get('email', '')
    contact_phone = block_data.get('contact_phone') or block_data.get('phone', '')
    check_in = block_data.get('check_in') or block_data.get('check_in_date')
    check_out = block_data.get('check_out') or block_data.get('check_out_date')
    cutoff_date = block_data.get('cutoff_date') or block_data.get('cutoff', check_in)
    
    # Create group block
    block = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'group_name': group_name,
        'organization': organization,
        'contact_name': contact_name,
        'contact_email': contact_email,
        'contact_phone': contact_phone,
        'check_in': check_in,
        'check_out': check_out,
        'total_rooms': block_data['total_rooms'],
        'rooms_picked_up': 0,
        'room_breakdown': block_data.get('room_breakdown', {}),
        'group_rate': block_data.get('group_rate') or block_data.get('rate_per_room', 100),
        'room_type': block_data.get('room_type', 'Standard'),
        'cutoff_date': cutoff_date,
        'billing_type': block_data.get('billing_type', 'master_account'),
        'status': 'tentative',
        'special_requirements': block_data.get('special_requirements'),
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.group_blocks.insert_one(block)
    
    # Create master folio if billing type is master_account
    if block['billing_type'] == 'master_account':
        master_folio = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'group_block_id': block['id'],
            'folio_type': 'group_master',
            'total_charges': 0.0,
            'total_payments': 0.0,
            'balance': 0.0,
            'status': 'open',
            'master_charges': ['room', 'breakfast', 'meeting_room'],
            'individual_charges': ['minibar', 'spa', 'telephone'],
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.folios.insert_one(master_folio)
        
        block['master_folio_id'] = master_folio['id']
        await db.group_blocks.update_one(
            {'id': block['id']},
            {'$set': {'master_folio_id': master_folio['id']}}
        )
    
    return {
        'success': True,
        'message': 'Grup bloğu başarıyla oluşturuldu',
        'block_id': block['id'],
        'group_name': group_name,
        'total_rooms': block_data['total_rooms']
    }



@router.get("/groups/blocks")
async def get_group_blocks(
    status: Optional[str] = None,
    date_range: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Grup bloklarını listele"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    # Date range filtering based on check_in (stored as YYYY-MM-DD string)
    if date_range:
        today = datetime.now(timezone.utc).date()
        range_start = None
        range_end = None

        if date_range == "today":
            range_start = today
            range_end = today
        elif date_range == "this_month":
            first_day = today.replace(day=1)
            # Find last day of month by going to first day of next month and subtracting one day
            if first_day.month == 12:
                next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
            else:
                next_month = first_day.replace(month=first_day.month + 1, day=1)
            last_day = next_month - timedelta(days=1)
            range_start = first_day
            range_end = last_day
        elif date_range == "next_30":
            range_start = today
            range_end = today + timedelta(days=30)
        elif date_range == "custom" and start_date and end_date:
            try:
                range_start = datetime.fromisoformat(start_date).date()
                range_end = datetime.fromisoformat(end_date).date()
            except Exception:
                range_start = None
                range_end = None

        if range_start and range_end:
            start_str = range_start.isoformat()
            end_str = range_end.isoformat()
            query['check_in'] = {'$gte': start_str, '$lte': end_str}
    
    blocks = await db.group_blocks.find(query, {'_id': 0}).sort('check_in', -1).to_list(100)
    
    return {
        'blocks': blocks,
        'total': len(blocks)
    }



@router.get("/groups/block/{block_id}")
async def get_group_block_details(
    block_id: str,
    current_user: User = Depends(get_current_user)
):
    """Grup bloğu detayları ve pickup tracking"""
    block = await db.group_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})
    
    if not block:
        raise HTTPException(status_code=404, detail="Grup bloğu bulunamadı")
    
    # Get all bookings in this group
    group_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'group_block_id': block_id
    }, {'_id': 0}).to_list(1000)
    
    # Calculate pickup stats
    rooms_picked_up = len(group_bookings)
    rooms_remaining = block['total_rooms'] - rooms_picked_up
    pickup_pct = (rooms_picked_up / block['total_rooms'] * 100) if block['total_rooms'] > 0 else 0
    
    # Update block pickup count
    await db.group_blocks.update_one(
        {'id': block_id},
        {'$set': {'rooms_picked_up': rooms_picked_up}}
    )
    
    return {
        'block': block,
        'pickup': {
            'total_rooms': block['total_rooms'],
            'rooms_picked_up': rooms_picked_up,
            'rooms_remaining': rooms_remaining,
            'pickup_percentage': round(pickup_pct, 2)
        },
        'bookings': group_bookings,
        'bookings_count': len(group_bookings)
    }



@router.post("/groups/rooming-list/{block_id}")
async def upload_rooming_list(
    block_id: str,
    rooming_list: List[dict],
    current_user: User = Depends(get_current_user)
):
    """Rooming list upload (Excel'den gelen data)"""
    from domains.pms.group_sales_models import RoomingListEntry
    
    # Verify block exists
    block = await db.group_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})
    
    if not block:
        raise HTTPException(status_code=404, detail="Grup bloğu bulunamadı")
    
    created_bookings = []
    errors = []
    
    for idx, entry_data in enumerate(rooming_list):
        try:
            entry = RoomingListEntry(**entry_data)
            
            # Create or find guest
            guest = await db.guests.find_one({
                'tenant_id': current_user.tenant_id,
                'name': entry.guest_name
            }, {'_id': 0})
            
            if not guest:
                # Create new guest
                guest = {
                    'id': str(uuid.uuid4()),
                    'tenant_id': current_user.tenant_id,
                    'name': entry.guest_name,
                    'email': entry.email,
                    'phone': entry.phone,
                    'passport_number': entry.passport_number,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                await db.guests.insert_one(guest)
            
            # Find available room of requested type
            room = await db.rooms.find_one({
                'tenant_id': current_user.tenant_id,
                'room_type': entry.room_type,
                'status': 'available'
            }, {'_id': 0})
            
            if not room:
                errors.append(f"Row {idx+1}: {entry.room_type} tipi oda mevcut değil")
                continue
            
            # Create booking
            booking = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'group_block_id': block_id,
                'check_in': entry.check_in,
                'check_out': entry.check_out,
                'status': 'confirmed',
                'adults': 2,
                'children': 0,
                'total_amount': block['group_rate'],
                'rate_type': 'group',
                'market_segment': 'group',
                'special_requests': entry.special_requests,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'created_by': current_user.id
            }
            
            from core.atomic_booking import create_booking_atomic, BookingConflictError
            try:
                await create_booking_atomic(booking)
            except BookingConflictError as e:
                errors.append(f"Row {idx+1}: {str(e)}")
                continue
            created_bookings.append({
                'booking_id': booking['id'],
                'guest_name': entry.guest_name,
                'room_number': room['room_number']
            })
            
        except Exception as e:
            errors.append(f"Row {idx+1}: {str(e)}")
    
    return {
        'success': True,
        'message': f'{len(created_bookings)} rezervasyon oluşturuldu',
        'created_bookings': created_bookings,
        'errors': errors,
        'total_processed': len(rooming_list),
        'successful': len(created_bookings),
        'failed': len(errors)
    }



@router.get("/groups/master-folio/{block_id}")
async def get_group_master_folio(
    block_id: str,
    current_user: User = Depends(get_current_user)
):
    """Grup master folio detayları"""
    # Get block
    block = await db.group_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})
    
    if not block:
        raise HTTPException(status_code=404, detail="Grup bloğu bulunamadı")
    
    # Get master folio
    master_folio = await db.folios.find_one({
        'group_block_id': block_id,
        'folio_type': 'group_master'
    }, {'_id': 0})
    
    if not master_folio:
        return {
            'block_id': block_id,
            'has_master_folio': False,
            'message': 'Bu grup için master folio oluşturulmamış'
        }
    
    # Get all charges on master folio
    charges = await db.folio_charges.find({
        'folio_id': master_folio['id'],
        'voided': False
    }, {'_id': 0}).to_list(1000)
    
    total_charges = sum([c.get('total', c.get('amount', 0)) for c in charges])
    
    # Get payments
    payments = await db.payments.find({
        'folio_id': master_folio['id']
    }, {'_id': 0}).to_list(1000)
    
    total_payments = sum([p.get('amount', 0) for p in payments])
    
    balance = total_charges - total_payments
    
    # Update folio totals
    await db.folios.update_one(
        {'id': master_folio['id']},
        {
            '$set': {
                'total_charges': total_charges,
                'total_payments': total_payments,
                'balance': balance
            }
        }
    )
    
    return {
        'block_id': block_id,
        'block_name': block['group_name'],
        'has_master_folio': True,
        'folio': {
            'id': master_folio['id'],
            'total_charges': round(total_charges, 2),
            'total_payments': round(total_payments, 2),
            'balance': round(balance, 2),
            'status': master_folio.get('status', 'open')
        },
        'charges': charges,
        'payments': payments,
        'charges_count': len(charges),
        'payments_count': len(payments)
    }



@router.post("/groups/block/{block_id}/release")
async def release_group_block(
    block_id: str,
    release_count: int,
    current_user: User = Depends(get_current_user)
):
    """Grup bloğundan oda serbest bırak"""
    block = await db.group_blocks.find_one({
        'id': block_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})
    
    if not block:
        raise HTTPException(status_code=404, detail="Grup bloğu bulunamadı")
    
    rooms_remaining = block['total_rooms'] - block['rooms_picked_up']
    
    if release_count > rooms_remaining:
        raise HTTPException(
            status_code=400, 
            detail=f"Sadece {rooms_remaining} oda serbest bırakılabilir"
        )
    
    new_total = block['total_rooms'] - release_count
    
    await db.group_blocks.update_one(
        {'id': block_id},
        {
            '$set': {
                'total_rooms': new_total,
                'release_date': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        'success': True,
        'message': f'{release_count} oda başarıyla serbest bırakıldı',
        'block_id': block_id,
        'previous_total': block['total_rooms'],
        'new_total': new_total,
        'released': release_count
    }


@router.get("/group-reservations")
async def get_group_reservations(current_user: User = Depends(get_current_user)):
    """Get all group reservations"""
    groups = await db.group_reservations.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('created_at', -1).to_list(100)
    
    return {'groups': groups, 'count': len(groups)}



@router.post("/group-reservations")
async def create_group_reservation(
    request: CreateGroupReservationRequest,
    current_user: User = Depends(get_current_user)
):
    """Create new group reservation"""
    group = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'group_name': request.group_name,
        'group_type': request.group_type,
        'contact_person': request.contact_person,
        'contact_email': request.contact_email,
        'contact_phone': request.contact_phone,
        'check_in_date': request.check_in_date,
        'check_out_date': request.check_out_date,
        'total_rooms': request.total_rooms,
        'adults_per_room': request.adults_per_room,
        'special_requests': request.special_requests,
        'status': 'pending',
        'rooms_assigned': 0,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'created_by': current_user.id
    }
    
    group_copy = group.copy()
    await db.group_reservations.insert_one(group_copy)
    return group



@router.get("/group-reservations/{group_id}")
async def get_group_reservation(
    group_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get group reservation details"""
    group = await db.group_reservations.find_one(
        {'id': group_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )
    
    if not group:
        raise HTTPException(status_code=404, detail="Group reservation not found")
    
    # Get individual bookings in this group
    bookings = await db.bookings.find(
        {'tenant_id': current_user.tenant_id, 'group_id': group_id},
        {'_id': 0}
    ).to_list(1000)
    
    group['bookings'] = bookings
    group['bookings_count'] = len(bookings)
    
    return group



@router.post("/group-reservations/{group_id}/assign-rooms")
async def assign_group_rooms(
    group_id: str,
    request: AssignGroupRoomsRequest,
    current_user: User = Depends(get_current_user)
):
    """Assign rooms to group reservation"""
    room_assignments = request.room_assignments
    group = await db.group_reservations.find_one(
        {'id': group_id, 'tenant_id': current_user.tenant_id}
    )
    
    if not group:
        raise HTTPException(status_code=404, detail="Group reservation not found")
    
    created_bookings = []
    
    for assignment in room_assignments:
        booking = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'group_id': group_id,
            'guest_name': assignment.get('guest_name', group['group_name']),
            'guest_email': assignment.get('guest_email', group['contact_email']),
            'guest_phone': assignment.get('guest_phone', group['contact_phone']),
            'check_in_date': group['check_in_date'],
            'check_out_date': group['check_out_date'],
            'room_type': assignment['room_type'],
            'room_id': assignment.get('room_id'),
            'adults': assignment.get('adults', group['adults_per_room']),
            'children': assignment.get('children', 0),
            'status': 'confirmed',
            'booking_source': 'group',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        from core.atomic_booking import create_booking_atomic, BookingConflictError
        try:
            await create_booking_atomic(booking)
        except BookingConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))
        created_bookings.append(booking)
    
    # Update group reservation
    await db.group_reservations.update_one(
        {'id': group_id},
        {
            '$set': {
                'rooms_assigned': len(created_bookings),
                'status': 'confirmed' if len(created_bookings) >= group['total_rooms'] else 'partial'
            }
        }
    )
    
    return {
        'message': f'Assigned {len(created_bookings)} rooms to group',
        'bookings': created_bookings
    }



@router.get("/block-reservations")
async def get_block_reservations(current_user: User = Depends(get_current_user)):
    """Get all block reservations"""
    blocks = await db.block_reservations.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('created_at', -1).to_list(100)
    
    return {'blocks': blocks, 'count': len(blocks)}



@router.post("/block-reservations")
async def create_block_reservation(
    request: CreateBlockReservationRequest,
    current_user: User = Depends(get_current_user)
):
    """Create room block reservation"""
    block = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'block_name': request.block_name,
        'room_type': request.room_type,
        'start_date': request.start_date,
        'end_date': request.end_date,
        'total_rooms': request.total_rooms,
        'rooms_used': 0,
        'rooms_available': request.total_rooms,
        'block_type': request.block_type,
        'release_date': request.release_date,
        'status': 'active',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'created_by': current_user.id
    }
    
    block_copy = block.copy()
    await db.block_reservations.insert_one(block_copy)
    return block



@router.post("/block-reservations/{block_id}/use-room")
async def use_block_room(
    block_id: str,
    request: UseBlockRoomRequest,
    current_user: User = Depends(get_current_user)
):
    """Use a room from block reservation"""
    guest_name = request.guest_name
    guest_email = request.guest_email
    block = await db.block_reservations.find_one(
        {'id': block_id, 'tenant_id': current_user.tenant_id}
    )
    
    if not block:
        raise HTTPException(status_code=404, detail="Block reservation not found")
    
    if block['rooms_available'] <= 0:
        raise HTTPException(status_code=400, detail="No rooms available in block")
    
    # Create booking from block
    booking = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'block_id': block_id,
        'guest_name': guest_name,
        'guest_email': guest_email,
        'check_in_date': block['start_date'],
        'check_out_date': block['end_date'],
        'room_type': block['room_type'],
        'status': 'confirmed',
        'booking_source': 'block',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    from core.atomic_booking import create_booking_atomic, BookingConflictError
    try:
        await create_booking_atomic(booking.copy())
    except BookingConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    
    # Update block availability
    await db.block_reservations.update_one(
        {'id': block_id},
        {
            '$inc': {'rooms_used': 1, 'rooms_available': -1}
        }
    )
    
    return {'message': 'Room used from block successfully', 'booking': booking}



@router.post("/block-reservations/{block_id}/release")
async def release_block_reservation(
    block_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release unused rooms from block"""
    block = await db.block_reservations.find_one(
        {'id': block_id, 'tenant_id': current_user.tenant_id}
    )
    
    if not block:
        raise HTTPException(status_code=404, detail="Block reservation not found")
    
    await db.block_reservations.update_one(
        {'id': block_id},
        {
            '$set': {
                'status': 'released',
                'released_at': datetime.now(timezone.utc).isoformat(),
                'released_by': current_user.id
            }
        }
    )
    
    return {
        'message': 'Block released successfully',
        'rooms_released': block['rooms_available']
    }


# ========================================
# 6. Multi-Property Management
# ========================================


