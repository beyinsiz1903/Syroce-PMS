"""
Advanced Features Endpoints
- OTA booking details with remarks
- Guest history & preferences
- Multi-room reservations
- RMS advanced analytics
- Messaging automation
- POS advanced features
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import uuid
import os
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db_name = os.environ.get('DB_NAME', 'hotel_pms')
db = client[db_name]

advanced_router = APIRouter()

# Mock user
class MockUser:
    def __init__(self):
        self.tenant_id = 'demo_hotel'
        self.id = 'demo_user'

async def get_current_user_mock():
    return MockUser()

# ========== MODELS ==========

class SpecialRequest(BaseModel):
    request_type: str
    description: str
    priority: str = 'normal'

class GuestPreference(BaseModel):
    category: str
    preference: str
    notes: Optional[str] = None

class BookingSource(BaseModel):
    source_type: str  # OTA, website, corporate, walk-in
    source_name: Optional[str] = None
    commission_rate: Optional[float] = None

class MultiRoomBooking(BaseModel):
    room_ids: List[str]
    guest_count: int
    rate_per_room: float

# ========== OTA & BOOKING ENHANCEMENTS ==========

@advanced_router.get("/bookings/{booking_id}/details")
async def get_booking_details(
    booking_id: str,
    current_user = Depends(get_current_user_mock)
):
    """Get detailed booking with OTA info, remarks, special requests"""
    booking = await db.bookings.find_one({'id': booking_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get special requests
    requests = await db.special_requests.find({'booking_id': booking_id}, {'_id': 0}).to_list(10)
    
    # Get source details
    source = await db.booking_sources.find_one({'booking_id': booking_id}, {'_id': 0})
    
    return {
        'booking': booking,
        'special_requests': requests,
        'source': source,
        'has_remarks': bool(booking.get('remarks')),
        'ota_details': source if source and source.get('source_type') == 'OTA' else None
    }

@advanced_router.post("/bookings/{booking_id}/special-requests")
async def add_special_request(
    booking_id: str,
    request: SpecialRequest,
    current_user = Depends(get_current_user_mock)
):
    """Add special request to booking"""
    special_req = {
        'id': str(uuid.uuid4()),
        'booking_id': booking_id,
        **request.dict(),
        'created_at': datetime.now(),
        'tenant_id': current_user.tenant_id
    }
    
    await db.special_requests.insert_one(special_req)
    return {'success': True, 'request_id': special_req['id']}

# ========== GUEST PROFILE ENHANCEMENTS ==========

@advanced_router.get("/guests/{guest_id}/history")
async def get_guest_history(
    guest_id: str,
    current_user = Depends(get_current_user_mock)
):
    """Get complete guest booking history"""
    bookings = await db.bookings.find(
        {'guest_id': guest_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('check_in', -1).to_list(100)
    
    # Calculate stats
    total_stays = len([b for b in bookings if b.get('status') == 'checked_out'])
    total_nights = sum(b.get('nights', 0) for b in bookings)
    total_revenue = sum(b.get('total_amount', 0) for b in bookings)
    
    return {
        'bookings': bookings,
        'statistics': {
            'total_stays': total_stays,
            'total_nights': total_nights,
            'total_revenue': total_revenue,
            'average_stay_length': total_nights / total_stays if total_stays > 0 else 0,
            'first_stay': bookings[-1].get('check_in') if bookings else None,
            'last_stay': bookings[0].get('check_in') if bookings else None
        }
    }

@advanced_router.get("/guests/{guest_id}/preferences")
async def get_guest_preferences(
    guest_id: str,
    current_user = Depends(get_current_user_mock)
):
    """Get guest preferences"""
    prefs = await db.guest_preferences.find(
        {'guest_id': guest_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(50)
    
    # Get tags
    guest = await db.guests.find_one({'id': guest_id}, {'_id': 0})
    
    return {
        'preferences': prefs,
        'tags': guest.get('tags', []) if guest else [],
        'vip': guest.get('vip', False) if guest else False,
        'blacklisted': guest.get('blacklisted', False) if guest else False,
        'notes': guest.get('notes', '') if guest else ''
    }

@advanced_router.post("/guests/{guest_id}/preferences")
async def add_guest_preference(
    guest_id: str,
    preference: GuestPreference,
    current_user = Depends(get_current_user_mock)
):
    """Add guest preference"""
    pref = {
        'id': str(uuid.uuid4()),
        'guest_id': guest_id,
        **preference.dict(),
        'tenant_id': current_user.tenant_id
    }
    
    await db.guest_preferences.insert_one(pref)
    return {'success': True, 'preference_id': pref['id']}

@advanced_router.put("/guests/{guest_id}/tags")
async def update_guest_tags(
    guest_id: str,
    tags: List[str],
    vip: bool = False,
    blacklisted: bool = False,
    current_user = Depends(get_current_user_mock)
):
    """Update guest tags (VIP, Blacklist, etc)"""
    await db.guests.update_one(
        {'id': guest_id},
        {'$set': {
            'tags': tags,
            'vip': vip,
            'blacklisted': blacklisted,
            'updated_at': datetime.now()
        }}
    )
    return {'success': True}

# ========== MULTI-ROOM & BOOKING ENHANCEMENTS ==========

@advanced_router.post("/bookings/multi-room")
async def create_multi_room_booking(
    booking: MultiRoomBooking,
    guest_name: str,
    check_in: str,
    check_out: str,
    current_user = Depends(get_current_user_mock)
):
    """Create multi-room booking"""
    bookings_created = []
    
    for idx, room_id in enumerate(booking.room_ids):
        booking_id = str(uuid.uuid4())
        new_booking = {
            'id': booking_id,
            'room_id': room_id,
            'guest_name': f"{guest_name}" + (f" - Room {idx+1}" if idx > 0 else ""),
            'check_in': check_in,
            'check_out': check_out,
            'guests_count': booking.guest_count // len(booking.room_ids),
            'rate': booking.rate_per_room,
            'total_amount': booking.rate_per_room,
            'status': 'confirmed',
            'multi_room_group': bookings_created[0] if bookings_created else booking_id,
            'tenant_id': current_user.tenant_id,
            'created_at': datetime.now()
        }
        
        from core.atomic_booking import create_booking_atomic, BookingConflictError
        try:
            await create_booking_atomic(new_booking)
        except BookingConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))
        bookings_created.append(booking_id)
    
    return {
        'success': True,
        'bookings_created': bookings_created,
        'room_count': len(booking.room_ids)
    }

@advanced_router.get("/bookings/{booking_id}/extra-charges")
async def get_extra_charges(
    booking_id: str,
    current_user = Depends(get_current_user_mock)
):
    """Get extra charges for booking"""
    charges = await db.extra_charges.find(
        {'booking_id': booking_id},
        {'_id': 0}
    ).to_list(100)
    
    total = sum(c.get('amount', 0) for c in charges)
    
    return {
        'charges': charges,
        'total': total,
        'count': len(charges)
    }

# ========== RMS ADVANCED FEATURES ==========

@advanced_router.get("/rms/demand-heatmap")
async def get_demand_heatmap(
    start_date: str,
    end_date: str,
    current_user = Depends(get_current_user_mock)
):
    """Get historical demand heatmap"""
    # Generate sample heatmap data
    current = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    
    heatmap = []
    while current <= end:
        # Mock demand score (0-100)
        import random
        demand_score = random.randint(30, 95)
        color = 'red' if demand_score > 80 else 'yellow' if demand_score > 60 else 'green'
        
        heatmap.append({
            'date': current.isoformat(),
            'demand_score': demand_score,
            'occupancy': demand_score * 0.9,
            'color': color,
            'day_of_week': current.strftime('%A')
        })
        current += timedelta(days=1)
    
    return {
        'heatmap': heatmap,
        'period': {'start': start_date, 'end': end_date}
    }

@advanced_router.get("/rms/compset-analysis")
async def get_compset_analysis(
    current_user = Depends(get_current_user_mock)
):
    """Get competitive set analysis"""
    # Mock compset data
    compset = [
        {
            'hotel_name': 'Our Hotel',
            'average_rate': 150.00,
            'occupancy': 78.5,
            'revpar': 117.75,
            'rating': 4.5,
            'is_our_hotel': True
        },
        {
            'hotel_name': 'Competitor A',
            'average_rate': 145.00,
            'occupancy': 82.0,
            'revpar': 118.90,
            'rating': 4.3
        },
        {
            'hotel_name': 'Competitor B',
            'average_rate': 165.00,
            'occupancy': 75.0,
            'revpar': 123.75,
            'rating': 4.6
        },
        {
            'hotel_name': 'Competitor C',
            'average_rate': 140.00,
            'occupancy': 80.0,
            'revpar': 112.00,
            'rating': 4.2
        }
    ]
    
    return {
        'compset': compset,
        'market_position': 2,
        'rate_gap': 5.00,
        'occupancy_gap': -3.5
    }

@advanced_router.get("/rms/price-recommendations")
async def get_price_recommendations(
    room_type: str,
    date: str,
    current_user = Depends(get_current_user_mock)
):
    """Get AI price recommendations with range"""
    # Mock recommendation
    base_price = 150.00
    
    return {
        'recommended_price': base_price,
        'price_range': {
            'min': base_price * 0.85,
            'max': base_price * 1.20,
            'optimal': base_price
        },
        'factors': {
            'demand': 'high',
            'competition': 'moderate',
            'historical': 'strong',
            'events': []
        },
        'confidence': 0.87
    }

# ========== MESSAGING AUTOMATION ==========

@advanced_router.get("/messaging/automation-flows")
async def get_automation_flows(
    current_user = Depends(get_current_user_mock)
):
    """Get automated message flows"""
    flows = await db.message_flows.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(50)
    
    return {'flows': flows, 'total': len(flows)}

@advanced_router.post("/messaging/automation-flows")
async def create_automation_flow(
    name: str,
    trigger: str,
    template_id: str,
    delay_hours: int = 0,
    current_user = Depends(get_current_user_mock)
):
    """Create automated message flow"""
    flow = {
        'id': str(uuid.uuid4()),
        'name': name,
        'trigger': trigger,  # pre_checkin, post_checkout, etc
        'template_id': template_id,
        'delay_hours': delay_hours,
        'active': True,
        'tenant_id': current_user.tenant_id,
        'created_at': datetime.now()
    }
    
    await db.message_flows.insert_one(flow)
    return {'success': True, 'flow_id': flow['id']}

# ========== HOUSEKEEPING ENHANCEMENTS ==========

@advanced_router.get("/housekeeping/room-assignments")
async def get_room_assignments(
    date: Optional[str] = None,
    current_user = Depends(get_current_user_mock)
):
    """Get room assignments for staff"""
    if not date:
        date = datetime.now().isoformat()
    
    assignments = await db.room_assignments.find(
        {'tenant_id': current_user.tenant_id, 'date': {'$gte': date}},
        {'_id': 0}
    ).to_list(200)
    
    # Group by staff
    by_staff = {}
    for assignment in assignments:
        staff_id = assignment['staff_id']
        if staff_id not in by_staff:
            by_staff[staff_id] = []
        by_staff[staff_id].append(assignment)
    
    return {
        'assignments': assignments,
        'by_staff': by_staff,
        'date': date
    }

@advanced_router.get("/housekeeping/cleaning-statistics")
async def get_cleaning_statistics(
    start_date: Optional[str] = None,
    current_user = Depends(get_current_user_mock)
):
    """Get cleaning time statistics"""
    # Mock stats
    return {
        'average_cleaning_time': 28.5,  # minutes
        'fastest_time': 18.0,
        'slowest_time': 45.0,
        'by_room_type': {
            'Standard': 25.0,
            'Deluxe': 32.0,
            'Suite': 48.0
        },
        'by_staff': [
            {'staff_name': 'Maria Garcia', 'avg_time': 24.5, 'rooms_cleaned': 156},
            {'staff_name': 'John Smith', 'avg_time': 27.0, 'rooms_cleaned': 142},
            {'staff_name': 'Sarah Johnson', 'avg_time': 26.5, 'rooms_cleaned': 148}
        ]
    }

# ========== POS ADVANCED ==========

@advanced_router.post("/pos/orders")
async def create_order(
    table_id: str,
    items: List[dict],
    current_user = Depends(get_current_user_mock)
):
    """Create POS order"""
    order_id = str(uuid.uuid4())
    total = sum(item['quantity'] * item['price'] for item in items)
    
    order = {
        'id': order_id,
        'table_id': table_id,
        'items': items,
        'subtotal': total,
        'tax': total * 0.1,
        'total': total * 1.1,
        'status': 'pending',
        'created_at': datetime.now(),
        'tenant_id': current_user.tenant_id
    }
    
    await db.pos_orders.insert_one(order)
    return {'success': True, 'order_id': order_id, 'total': order['total']}

@advanced_router.get("/pos/orders/{order_id}")
async def get_order(
    order_id: str,
    current_user = Depends(get_current_user_mock)
):
    """Get order details"""
    order = await db.pos_orders.find_one({'id': order_id}, {'_id': 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@advanced_router.put("/pos/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    new_status: str,
    current_user = Depends(get_current_user_mock)
):
    """Update order status"""
    await db.pos_orders.update_one(
        {'id': order_id},
        {'$set': {'status': new_status, 'updated_at': datetime.now()}}
    )
    return {'success': True}

# Export router
__all__ = ['advanced_router']
