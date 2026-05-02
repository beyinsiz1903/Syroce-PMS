"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: revenue_reports) ───


@router.get("/revenue/pickup-report")
@cached(ttl=300, key_prefix="rev_pickup_report")  # 5dk cache (Tur 2 fix)
async def get_pickup_report(
    start_date: str | None = None,
    end_date: str | None = None,
    format: str = 'json',
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pickup report with export capability (JSON, CSV ready)"""
    current_user = await get_current_user(credentials)

    if not start_date:
        start_date = datetime.now(UTC).replace(day=1)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        end_date = start_date + timedelta(days=30)
    else:
        end_date = datetime.fromisoformat(end_date)

    # Get booking pace by arrival date
    pickup_report = []

    # Iterate through each day in range
    current_date = start_date
    while current_date <= end_date:
        # Get bookings for this arrival date
        day_bookings = []

        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': {
                '$gte': current_date,
                '$lt': current_date + timedelta(days=1)
            },
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }):
            days_before = (current_date - booking.get('created_at')).days if booking.get('created_at') else 0
            day_bookings.append({
                'booking_id': booking.get('id'),
                'created_at': booking.get('created_at').date().isoformat() if booking.get('created_at') else None,
                'days_before_arrival': days_before,
                'room_nights': booking.get('nights', 1),
                'revenue': booking.get('total_amount', 0)
            })

        # Aggregate data
        total_rooms = len(day_bookings)
        total_revenue = sum(b['revenue'] for b in day_bookings)

        # Group by booking window
        booking_windows = {
            '0-7_days': 0,
            '8-14_days': 0,
            '15-30_days': 0,
            '31-60_days': 0,
            '61+_days': 0
        }

        for booking in day_bookings:
            days = booking['days_before_arrival']
            if days <= 7:
                booking_windows['0-7_days'] += 1
            elif days <= 14:
                booking_windows['8-14_days'] += 1
            elif days <= 30:
                booking_windows['15-30_days'] += 1
            elif days <= 60:
                booking_windows['31-60_days'] += 1
            else:
                booking_windows['61+_days'] += 1

        pickup_report.append({
            'arrival_date': current_date.date().isoformat(),
            'total_rooms': total_rooms,
            'total_revenue': total_revenue,
            'booking_windows': booking_windows
        })

        current_date += timedelta(days=1)

    # If CSV format requested, prepare for export
    if format == 'csv':
        # Return data in CSV-friendly format
        csv_data = []
        for row in pickup_report:
            csv_data.append({
                'Arrival Date': row['arrival_date'],
                'Total Rooms': row['total_rooms'],
                'Total Revenue': row['total_revenue'],
                '0-7 Days': row['booking_windows']['0-7_days'],
                '8-14 Days': row['booking_windows']['8-14_days'],
                '15-30 Days': row['booking_windows']['15-30_days'],
                '31-60 Days': row['booking_windows']['31-60_days'],
                '61+ Days': row['booking_windows']['61+_days']
            })

        return {
            'format': 'csv',
            'data': csv_data,
            'filename': f"pickup_report_{start_date.date()}_{end_date.date()}.csv"
        }

    return {
        'format': 'json',
        'date_range': {
            'start': start_date.date().isoformat(),
            'end': end_date.date().isoformat()
        },
        'pickup_report': pickup_report,
        'summary': {
            'total_rooms': sum(r['total_rooms'] for r in pickup_report),
            'total_revenue': sum(r['total_revenue'] for r in pickup_report)
        }
    }




@router.get("/revenue/compset-analysis")
async def get_compset_analysis(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get competitive set analysis"""
    current_user = await get_current_user(credentials)

    # Get competitor data (would be manually entered or API integrated)
    competitors = []

    async for comp in db.competitors.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }):
        # Get their rates (if available)
        latest_rate = await db.competitor_rates.find_one(
            {
                'competitor_id': comp.get('id'),
                'tenant_id': current_user.tenant_id
            },
            sort=[('date', -1)]
        )

        competitors.append({
            'competitor_id': comp.get('id'),
            'competitor_name': comp.get('name'),
            'star_rating': comp.get('star_rating'),
            'location': comp.get('location'),
            'distance_km': comp.get('distance_km'),
            'current_adr': latest_rate.get('adr') if latest_rate else 0,
            'current_occupancy': latest_rate.get('occupancy_pct') if latest_rate else 0,
            'last_updated': latest_rate.get('date').isoformat() if latest_rate and latest_rate.get('date') else None
        })

    # Get own property data
    today = datetime.now(UTC)
    own_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    })

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    own_occupancy = (own_bookings / total_rooms * 100) if total_rooms > 0 else 0

    # Calculate own ADR
    own_adr = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today - timedelta(days=30)},
        'status': {'$in': ['checked_in', 'checked_out']}
    }):
        own_adr += booking.get('room_rate', 0)

    booking_count = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today - timedelta(days=30)},
        'status': {'$in': ['checked_in', 'checked_out']}
    })

    own_adr = own_adr / booking_count if booking_count > 0 else 0

    return {
        'own_property': {
            'adr': own_adr,
            'occupancy': own_occupancy,
            'revpar': own_adr * (own_occupancy / 100)
        },
        'competitors': competitors,
        'compset_count': len(competitors),
        'analysis_date': today.date().isoformat()
    }




@router.get("/revenue/market-share")
async def get_market_share(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get market share analysis"""
    current_user = await get_current_user(credentials)

    # Calculate market share based on bookings and revenue
    today = datetime.now(UTC)
    last_30_days = today - timedelta(days=30)

    # Own performance
    own_rooms = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': last_30_days},
        'status': {'$in': ['checked_in', 'checked_out']}
    })

    own_revenue = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': last_30_days},
        'status': {'$in': ['checked_in', 'checked_out']}
    }):
        own_revenue += booking.get('total_amount', 0)

    # Market data (would need competitor API or manual entry)
    # For now, estimating based on competitor count and average
    total_market_rooms = own_rooms  # Base
    total_market_revenue = own_revenue  # Base

    competitor_count = await db.competitors.count_documents({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    })

    # Estimate market (assuming similar performance)
    if competitor_count > 0:
        total_market_rooms += (own_rooms * competitor_count)
        total_market_revenue += (own_revenue * competitor_count)

    room_share = (own_rooms / total_market_rooms * 100) if total_market_rooms > 0 else 0
    revenue_share = (own_revenue / total_market_revenue * 100) if total_market_revenue > 0 else 0

    # Calculate fair share (1 / number of properties in compset)
    fair_share = 100 / (competitor_count + 1) if competitor_count >= 0 else 100

    return {
        'period': '30_days',
        'own_performance': {
            'room_nights': own_rooms,
            'revenue': own_revenue
        },
        'market_totals': {
            'room_nights': total_market_rooms,
            'revenue': total_market_revenue
        },
        'market_share': {
            'room_share_pct': room_share,
            'revenue_share_pct': revenue_share,
            'fair_share_pct': fair_share
        },
        'performance_index': {
            'room_mpi': (room_share / fair_share * 100) if fair_share > 0 else 100,
            'revenue_rgi': (revenue_share / fair_share * 100) if fair_share > 0 else 100
        }
    }


# --------------------------------------------------------------------------
# IT & Security - User Activity Logs, API Rate Limits
# --------------------------------------------------------------------------

