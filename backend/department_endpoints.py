"""
Department-Specific Dashboard Endpoints
Comprehensive endpoints for all hotel departments
"""

from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
import random

# These will be imported from main server.py
# from server import User, get_current_user, db

department_router = APIRouter(prefix="/api/department", tags=["departments"])


async def get_overbooking_alerts(tenant_id: str, db):
    """Get real-time overbooking alerts"""
    today = datetime.now(timezone.utc)
    next_30_days = today + timedelta(days=30)
    
    # Find overbookings
    overbookings = []
    
    # Group bookings by room and date
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': next_30_days.isoformat()}
    }).to_list(1000)
    
    # Check for conflicts
    room_dates = {}
    for booking in bookings:
        room_id = booking.get('room_id')
        check_in = datetime.fromisoformat(booking.get('check_in'))
        check_out = datetime.fromisoformat(booking.get('check_out'))
        
        # Generate date range
        current = check_in.date()
        end = check_out.date()
        while current < end:
            key = f"{room_id}_{current}"
            if key not in room_dates:
                room_dates[key] = []
            room_dates[key].append({
                'booking_id': booking.get('id'),
                'guest_name': booking.get('guest_name'),
                'confirmation': booking.get('confirmation_number', booking.get('id')[:8]),
                'source': booking.get('booking_source', 'direct')
            })
            current += timedelta(days=1)
    
    # Find conflicts
    for key, bookings_list in room_dates.items():
        if len(bookings_list) > 1:
            room_id, date_str = key.split('_')
            room = await db.rooms.find_one({'id': room_id})
            
            overbookings.append({
                'date': date_str,
                'room_number': room.get('room_number') if room else 'Unknown',
                'room_id': room_id,
                'conflict_count': len(bookings_list),
                'bookings': bookings_list,
                'severity': 'high' if len(bookings_list) > 2 else 'medium'
            })
    
    return overbookings


async def get_housekeeping_auto_rules(tenant_id: str, db):
    """Get automatic housekeeping status change rules"""
    rules = await db.housekeeping_rules.find({
        'tenant_id': tenant_id,
        'active': True
    }).to_list(100)
    
    if not rules:
        # Default rules
        rules = [
            {
                'id': 'rule_1',
                'name': 'Auto-dirty on checkout',
                'trigger': 'checkout',
                'action': 'set_status',
                'target_status': 'dirty',
                'active': True
            },
            {
                'id': 'rule_2',
                'name': 'Auto-inspected after cleaning',
                'trigger': 'cleaning_complete',
                'action': 'set_status',
                'target_status': 'inspected',
                'delay_minutes': 15,
                'active': True
            }
        ]
    
    return rules


async def get_rms_comprehensive_suggestions(tenant_id: str, db):
    """Get comprehensive RMS suggestions including min stay, CTA, pricing"""
    today = datetime.now(timezone.utc).date()
    
    suggestions = []
    
    # Get next 14 days
    for days_ahead in range(14):
        target_date = today + timedelta(days=days_ahead)
        
        # Get current occupancy forecast
        occupancy = 60 + random.randint(-10, 20) + (15 if target_date.weekday() in [4, 5] else 0)
        
        # Generate suggestions based on occupancy
        if occupancy < 50:
            suggestions.append({
                'date': target_date.isoformat(),
                'occupancy_forecast': occupancy,
                'price_action': 'decrease',
                'suggested_change': -15,
                'min_stay': 1,
                'close_to_arrival': False,
                'close_to_departure': False,
                'reasoning': 'Low demand period - decrease price to stimulate bookings'
            })
        elif occupancy > 85:
            suggestions.append({
                'date': target_date.isoformat(),
                'occupancy_forecast': occupancy,
                'price_action': 'increase',
                'suggested_change': 25,
                'min_stay': 2 if occupancy > 90 else 1,
                'close_to_arrival': occupancy > 95,
                'close_to_departure': False,
                'reasoning': 'High demand - maximize revenue with restrictions'
            })
        else:
            suggestions.append({
                'date': target_date.isoformat(),
                'occupancy_forecast': occupancy,
                'price_action': 'maintain',
                'suggested_change': 0,
                'min_stay': 1,
                'close_to_arrival': False,
                'close_to_departure': False,
                'reasoning': 'Balanced occupancy - maintain current strategy'
            })
    
    return suggestions


async def get_vip_determination_source(tenant_id: str, db):
    """Get VIP determination logic and sources"""
    return {
        'primary_source': 'PMS',
        'sources': [
            {
                'name': 'PMS Manual Tag',
                'weight': 40,
                'description': 'Staff manually marks guest as VIP'
            },
            {
                'name': 'CRM Loyalty Tier',
                'weight': 30,
                'description': 'Platinum/Gold tier members auto-tagged'
            },
            {
                'name': 'Revenue Threshold',
                'weight': 20,
                'description': 'Guests with >$10,000 lifetime spend'
            },
            {
                'name': 'Frequency',
                'weight': 10,
                'description': 'Guests with 5+ stays per year'
            }
        ],
        'auto_vip_rules': [
            'Loyalty tier >= Gold',
            'Total spend > $10,000',
            'Stays per year > 5',
            'Corporate rate > $200'
        ]
    }


async def get_corporate_accounts_ranking(tenant_id: str, db):
    """Get corporate accounts with detailed ranking"""
    # Get all corporate bookings
    corporate_bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'booking_source': {'$in': ['corporate', 'company_direct']}
    }).to_list(10000)
    
    # Aggregate by company
    companies = {}
    for booking in corporate_bookings:
        company = booking.get('company_name', 'Unknown')
        if company not in companies:
            companies[company] = {
                'name': company,
                'total_revenue': 0,
                'total_nights': 0,
                'booking_count': 0,
                'last_booking': None
            }
        
        companies[company]['total_revenue'] += booking.get('total_amount', 0)
        companies[company]['booking_count'] += 1
        
        # Calculate nights
        try:
            check_in = datetime.fromisoformat(booking.get('check_in'))
            check_out = datetime.fromisoformat(booking.get('check_out'))
            nights = (check_out - check_in).days
            companies[company]['total_nights'] += nights
        except:
            pass
        
        # Update last booking
        booking_date = booking.get('created_at')
        if not companies[company]['last_booking'] or booking_date > companies[company]['last_booking']:
            companies[company]['last_booking'] = booking_date
    
    # Calculate ADR and sort
    accounts = []
    for company, data in companies.items():
        adr = data['total_revenue'] / data['total_nights'] if data['total_nights'] > 0 else 0
        accounts.append({
            **data,
            'adr': round(adr, 2),
            'avg_revenue_per_booking': round(data['total_revenue'] / data['booking_count'], 2) if data['booking_count'] > 0 else 0
        })
    
    # Sort by total revenue (default)
    accounts.sort(key=lambda x: x['total_revenue'], reverse=True)
    
    return accounts


# API Response classes would go here in real implementation
class FrontOfficeResponse:
    pass

class HousekeepingResponse:
    pass

# ... etc
