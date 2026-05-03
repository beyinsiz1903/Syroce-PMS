"""
PMS / Dashboard Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Dashboard"])


# ── Inline Models ──

class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0



class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: list[BudgetMonth]


@router.get("/dashboard/role-based")
@cached(ttl=300, key_prefix="dashboard_role_based", role_aware=True)  # v63 Bug CX: role-aware key
async def get_role_based_dashboard(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    """Role-based dashboard data - GM, Owner, Front Desk, Housekeeping"""
    today = datetime.now(UTC)
    today_start = datetime.combine(today.date(), datetime.min.time()).replace(tzinfo=UTC)
    today_end = datetime.combine(today.date(), datetime.max.time()).replace(tzinfo=UTC)

    today_start_iso = today_start.isoformat()
    today_end_iso = today_end.isoformat()
    tid = current_user.tenant_id

    # Base data for all roles — paralel iki sayim
    total_rooms, occupied_rooms = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': tid}),
        db.bookings.count_documents({'tenant_id': tid, 'status': 'checked_in'}),
    )

    # Role-specific data
    if current_user.role in ['admin', 'supervisor']:  # GM/Manager
        # Tum bagimsiz sorgular paralel — count'lar + booking listesi + revenue agg + hk count
        arrivals_today, departures_today, candidate_bookings, revenue_doc, hk_tasks_completed = await asyncio.gather(
            db.bookings.count_documents({
                'tenant_id': tid,
                'check_in': {'$gte': today_start_iso, '$lte': today_end_iso},
            }),
            db.bookings.count_documents({
                'tenant_id': tid,
                'check_out': {'$gte': today_start_iso, '$lte': today_end_iso},
            }),
            db.bookings.find({
                'tenant_id': tid,
                'check_in': {'$gte': today_start_iso, '$lte': today_end_iso},
                'status': {'$in': ['confirmed', 'guaranteed']},
            }, {'_id': 0, 'guest_id': 1, 'room_number': 1, 'check_in': 1}).limit(10).to_list(length=10),
            db.folio_charges.aggregate([
                {'$match': {
                    'tenant_id': tid,
                    'date': {'$gte': today_start_iso, '$lte': today_end_iso},
                    'voided': False,
                }},
                {'$group': {'_id': None, 'total': {'$sum': '$total'}}},
            ]).to_list(1),
            db.housekeeping_tasks.count_documents({
                'tenant_id': tid,
                'completed_at': {'$gte': today_start_iso, '$lte': today_end_iso},
            }),
        )

        # Get VIP arrivals (1 guest query)
        guest_ids = [b.get('guest_id') for b in candidate_bookings if b.get('guest_id')]
        guests_by_id = {}
        if guest_ids:
            async for g in db.guests.find(
                {'id': {'$in': guest_ids}, 'tenant_id': tid, 'vip': True},
                {'_id': 0, 'id': 1, 'name': 1, 'preferences': 1, 'vip': 1},
            ):
                guests_by_id[g['id']] = g
        vip_arrivals = []
        for booking in candidate_bookings:
            guest = guests_by_id.get(booking.get('guest_id'))
            if guest:
                vip_arrivals.append({
                    'guest_name': guest.get('name'),
                    'room_number': booking.get('room_number'),
                    'check_in': booking.get('check_in'),
                    'preferences': guest.get('preferences', 'None')
                })

        revenue_today = (revenue_doc[0]['total'] if revenue_doc else 0) or 0

        return {
            'role': current_user.role,
            'dashboard_type': 'gm',
            'occupancy': {
                'current': round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 1),
                'occupied_rooms': occupied_rooms,
                'total_rooms': total_rooms
            },
            'today_movements': {
                'arrivals': arrivals_today,
                'departures': departures_today,
                'stayovers': occupied_rooms - arrivals_today
            },
            'revenue_today': round(revenue_today, 2),
            'vip_arrivals': vip_arrivals[:5],
            'priorities': {
                'pending_checkins': arrivals_today,
                'pending_checkouts': departures_today,
                'housekeeping_completed': hk_tasks_completed
            }
        }

    elif current_user.role == 'front_desk':
        # Front desk specific (batched)
        fd_bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$gte': today_start.isoformat(), '$lte': today_end.isoformat()},
            'status': {'$in': ['confirmed', 'guaranteed']}
        }, {'_id': 0, 'id': 1, 'guest_name': 1, 'room_number': 1, 'check_in': 1, 'status': 1, 'room_id': 1}).limit(20).to_list(length=20)
        room_ids = [b.get('room_id') for b in fd_bookings if b.get('room_id')]
        rooms_by_id = {}
        if room_ids:
            async for r in db.rooms.find(
                {'id': {'$in': room_ids}, 'tenant_id': current_user.tenant_id},
                {'_id': 0, 'id': 1, 'status': 1},
            ):
                rooms_by_id[r['id']] = r
        arrivals = []
        for booking in fd_bookings:
            room = rooms_by_id.get(booking.get('room_id'))
            arrivals.append({
                'id': booking.get('id'),
                'guest_name': booking.get('guest_name'),
                'room_number': booking.get('room_number'),
                'check_in_time': booking.get('check_in'),
                'status': booking.get('status'),
                'room_ready': room.get('status') in ['available', 'inspected'] if room else False
            })

        return {
            'role': current_user.role,
            'dashboard_type': 'front_desk',
            'occupancy': round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 1),
            'arrivals_today': arrivals,
            'in_house_guests': occupied_rooms
        }

    elif current_user.role == 'housekeeping':
        # 4 bagimsiz count paralel — N+1 fix
        dirty_rooms, cleaning_rooms, inspected_rooms, departures_today = await asyncio.gather(
            db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'dirty'}),
            db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'cleaning'}),
            db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'inspected'}),
            db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'check_out': {'$gte': today_start.isoformat(), '$lte': today_end.isoformat()},
            }),
        )
        return {
            'role': current_user.role,
            'dashboard_type': 'housekeeping',
            'room_status': {
                'dirty': dirty_rooms,
                'cleaning': cleaning_rooms,
                'inspected': inspected_rooms,
                'ready': inspected_rooms
            },
            'occupancy': occupied_rooms,
            'departures_today': departures_today,
        }

    else:
        # Default minimal data
        return {
            'role': current_user.role,
            'dashboard_type': 'basic',
            'occupancy': round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 1)
        }



@router.get("/dashboard/gm-forecast")
@cached(ttl=600, key_prefix="gm_forecast")  # Cache for 10 minutes
async def get_gm_forecast_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v71 Bug DH
):
    """Get 30-day forecast summary for GM Dashboard"""
    today = datetime.now(UTC).date()
    thirty_days = today + timedelta(days=30)

    # Get existing forecasts
    forecasts = await db.demand_forecasts.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': today.isoformat(), '$lte': thirty_days.isoformat()}
    }).sort('date', 1).to_list(30)

    if not forecasts or len(forecasts) < 7:
        # Generate forecast if not exists
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        if total_rooms == 0:
            total_rooms = 40

        forecasts = []
        for days_ahead in range(30):
            forecast_date = today + timedelta(days=days_ahead)
            # Simple ML-inspired forecast
            base_occupancy = 65
            weekend_boost = 15 if forecast_date.weekday() in [4, 5] else 0
            seasonal_factor = 10 if forecast_date.month in [6, 7, 8, 12] else 0

            occupancy = min(95, base_occupancy + weekend_boost + seasonal_factor + random.randint(-5, 5))
            demand_score = round(occupancy / 100 * total_rooms)

            forecasts.append({
                'date': forecast_date.isoformat(),
                'predicted_occupancy': occupancy,
                'predicted_demand': demand_score,
                'confidence': 0.85
            })

    # Calculate summary metrics
    avg_occupancy = sum(f.get('predicted_occupancy', 0) for f in forecasts) / len(forecasts) if forecasts else 0
    peak_days = [f for f in forecasts if f.get('predicted_occupancy', 0) > 85]
    low_days = [f for f in forecasts if f.get('predicted_occupancy', 0) < 50]

    return {
        'period': {
            'start': today.isoformat(),
            'end': thirty_days.isoformat(),
            'days': 30
        },
        'summary': {
            'avg_occupancy': round(avg_occupancy, 1),
            'peak_days_count': len(peak_days),
            'low_days_count': len(low_days)
        },
        'daily_forecast': forecasts[:30],
        'alerts': [
            {'type': 'high_demand', 'date': d['date'], 'occupancy': d['predicted_occupancy']}
            for d in peak_days[:5]
        ]
    }


@router.get("/dashboard/employee-performance")
@cached(ttl=600, key_prefix="dashboard_employee_performance")  # Cache for 10 minutes
async def get_employee_performance(
    start_date: str | None = None,
    end_date: str | None = None,
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v71 Bug DH (HR)
):
    """
    Get employee performance metrics
    - HK staff: average cleaning time per room
    - Front Desk: average check-in duration
    - Overall productivity metrics
    """
    # Default to last 30 days
    if not end_date:
        end_dt = datetime.now(UTC)
    else:
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)

    if not start_date:
        start_dt = end_dt - timedelta(days=30)
    else:
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)

    # Housekeeping Performance
    hk_pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'status': 'completed',
                'completed_at': {
                    '$gte': start_dt.isoformat(),
                    '$lte': end_dt.isoformat()
                }
            }
        },
        {
            '$addFields': {
                'started_datetime': {'$dateFromString': {'dateString': '$started_at'}},
                'completed_datetime': {'$dateFromString': {'dateString': '$completed_at'}}
            }
        },
        {
            '$addFields': {
                'duration_minutes': {
                    '$divide': [
                        {'$subtract': ['$completed_datetime', '$started_datetime']},
                        60000  # Convert milliseconds to minutes
                    ]
                }
            }
        },
        {
            '$group': {
                '_id': '$assigned_to',
                'total_tasks': {'$sum': 1},
                'avg_duration': {'$avg': '$duration_minutes'},
                'min_duration': {'$min': '$duration_minutes'},
                'max_duration': {'$max': '$duration_minutes'}
            }
        },
        {
            '$sort': {'avg_duration': 1}  # Fastest first
        }
    ]

    hk_performance = []
    async for staff in db.housekeeping_tasks.aggregate(hk_pipeline):
        avg = staff.get('avg_duration')
        if avg is None:
            rating = 'N/A'
        elif avg < 20:
            rating = 'Excellent'
        elif avg < 30:
            rating = 'Good'
        else:
            rating = 'Needs Improvement'
        hk_performance.append({
            'staff_name': staff.get('_id') or 'Unassigned',
            'department': 'housekeeping',
            'total_tasks': staff.get('total_tasks', 0),
            'avg_duration_minutes': round(avg, 1) if avg is not None else 0,
            'min_duration_minutes': round(staff['min_duration'], 1) if staff.get('min_duration') is not None else 0,
            'max_duration_minutes': round(staff['max_duration'], 1) if staff.get('max_duration') is not None else 0,
            'efficiency_rating': rating
        })

    # Front Desk Performance (Check-in duration)
    # Calculate from audit logs
    checkin_logs = []
    async for log in db.audit_logs.find({
        'tenant_id': current_user.tenant_id,
        'action': 'CHECKIN',
        'timestamp': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        checkin_logs.append(log)

    fd_performance = {}
    for log in checkin_logs:
        user_id = log.get('user_id')
        user_name = log.get('user_name', 'Unknown')

        if user_id not in fd_performance:
            fd_performance[user_id] = {
                'staff_name': user_name,
                'department': 'front_desk',
                'total_checkins': 0,
                'durations': []
            }

        fd_performance[user_id]['total_checkins'] += 1
        # Simulated duration (in real system, track actual time)
        fd_performance[user_id]['durations'].append(5)  # Average 5 minutes per check-in

    fd_staff_performance = []
    for user_id, data in fd_performance.items():
        if data['durations']:
            avg_duration = sum(data['durations']) / len(data['durations'])
            fd_staff_performance.append({
                'staff_name': data['staff_name'],
                'department': 'front_desk',
                'total_checkins': data['total_checkins'],
                'avg_checkin_duration_minutes': round(avg_duration, 1),
                'efficiency_rating': 'Excellent' if avg_duration < 5 else 'Good' if avg_duration < 8 else 'Needs Improvement'
            })

    # Combined performance
    all_performance = hk_performance + fd_staff_performance

    # Filter by department if specified
    if department:
        all_performance = [p for p in all_performance if p['department'] == department]

    return {
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'department_filter': department,
        'total_staff': len(all_performance),
        'performance_by_staff': all_performance,
        'summary': {
            'housekeeping': {
                'staff_count': len(hk_performance),
                'avg_cleaning_time': round(sum(p['avg_duration_minutes'] for p in hk_performance) / len(hk_performance), 1) if hk_performance else 0,
                'total_tasks_completed': sum(p['total_tasks'] for p in hk_performance)
            },
            'front_desk': {
                'staff_count': len(fd_staff_performance),
                'avg_checkin_time': round(sum(p['avg_checkin_duration_minutes'] for p in fd_staff_performance) / len(fd_staff_performance), 1) if fd_staff_performance else 0,
                'total_checkins': sum(p['total_checkins'] for p in fd_staff_performance)
            }
        }
    }




@router.get("/dashboard/guest-satisfaction-trends")
@cached(ttl=600, key_prefix="dashboard_guest_satisfaction")  # Cache for 10 minutes
async def get_guest_satisfaction_trends(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    """
    Get guest satisfaction trends (NPS - Net Promoter Score)
    - Last 7 days
    - Last 30 days
    - Trend analysis
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    # Get all feedback/reviews in the period
    [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'created_at': {
                    '$gte': start_dt.isoformat(),
                    '$lte': end_dt.isoformat()
                }
            }
        }
    ]

    # 3 bagimsiz feedback kaynagi paralel cek — N+1 fix
    survey_docs, review_docs, dept_docs = await asyncio.gather(
        db.survey_responses.find({
            'tenant_id': current_user.tenant_id,
            'submitted_at': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()},
        }).to_list(5000),
        db.external_reviews.find({
            'tenant_id': current_user.tenant_id,
            'review_date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()},
        }).to_list(5000),
        db.department_feedback.find({
            'tenant_id': current_user.tenant_id,
            'created_at': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()},
        }).to_list(5000),
    )

    all_feedback = []
    for response in survey_docs:
        all_feedback.append({
            'date': response.get('submitted_at', ''),
            'rating': response.get('overall_rating', 0),
            'source': 'survey',
            'sentiment': response.get('sentiment', 'neutral'),
        })
    for review in review_docs:
        all_feedback.append({
            'date': review.get('review_date', ''),
            'rating': review.get('rating', 0),
            'source': review.get('platform', 'external'),
            'sentiment': review.get('sentiment', 'neutral'),
        })
    for feedback in dept_docs:
        all_feedback.append({
            'date': feedback.get('created_at', ''),
            'rating': feedback.get('rating', 0),
            'source': 'department',
            'sentiment': feedback.get('sentiment', 'neutral'),
        })

    # Calculate NPS (Net Promoter Score)
    # NPS = % Promoters (9-10) - % Detractors (0-6)
    # Scale: Convert 5-star rating to 10-point scale
    promoters = 0
    passives = 0
    detractors = 0
    total_ratings = []

    for item in all_feedback:
        rating = item['rating']
        total_ratings.append(rating)

        # Convert to 10-point scale if needed (assuming 5-star scale)
        if rating <= 5:
            rating_10 = rating * 2
        else:
            rating_10 = rating

        if rating_10 >= 9:
            promoters += 1
        elif rating_10 >= 7:
            passives += 1
        else:
            detractors += 1

    total_responses = len(all_feedback)

    if total_responses > 0:
        nps_score = ((promoters - detractors) / total_responses) * 100
        avg_rating = sum(total_ratings) / total_responses
    else:
        nps_score = 0
        avg_rating = 0

    # Group by date for trend
    daily_ratings = {}
    for item in all_feedback:
        date_str = item['date'][:10]  # Get YYYY-MM-DD
        if date_str not in daily_ratings:
            daily_ratings[date_str] = []
        daily_ratings[date_str].append(item['rating'])

    trend_data = []
    for date_str in sorted(daily_ratings.keys()):
        ratings = daily_ratings[date_str]
        trend_data.append({
            'date': date_str,
            'avg_rating': round(sum(ratings) / len(ratings), 2),
            'count': len(ratings)
        })

    # Calculate 7-day vs 30-day comparison
    seven_days_ago = end_dt - timedelta(days=7)
    recent_feedback = [f for f in all_feedback if datetime.fromisoformat(f['date']) >= seven_days_ago]

    if recent_feedback:
        recent_avg = sum(f['rating'] for f in recent_feedback) / len(recent_feedback)
        recent_nps_promoters = sum(1 for f in recent_feedback if f['rating'] >= 4.5)
        recent_nps_detractors = sum(1 for f in recent_feedback if f['rating'] < 3.5)
        recent_nps = ((recent_nps_promoters - recent_nps_detractors) / len(recent_feedback)) * 100 if recent_feedback else 0
    else:
        recent_avg = 0
        recent_nps = 0

    return {
        'period_days': days,
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'nps_score': round(nps_score, 1),
        'nps_category': 'Excellent' if nps_score > 70 else 'Good' if nps_score > 30 else 'Fair' if nps_score > 0 else 'Needs Improvement',
        'avg_rating': round(avg_rating, 2),
        'total_responses': total_responses,
        'response_breakdown': {
            'promoters': promoters,
            'promoters_pct': round((promoters / total_responses * 100), 1) if total_responses > 0 else 0,
            'passives': passives,
            'passives_pct': round((passives / total_responses * 100), 1) if total_responses > 0 else 0,
            'detractors': detractors,
            'detractors_pct': round((detractors / total_responses * 100), 1) if total_responses > 0 else 0
        },
        'last_7_days': {
            'avg_rating': round(recent_avg, 2),
            'nps_score': round(recent_nps, 1),
            'response_count': len(recent_feedback)
        },
        'trend_data': trend_data,
        'sentiment_breakdown': {
            'positive': sum(1 for f in all_feedback if f['sentiment'] == 'positive'),
            'neutral': sum(1 for f in all_feedback if f['sentiment'] == 'neutral'),
            'negative': sum(1 for f in all_feedback if f['sentiment'] == 'negative')
        }
    }




@router.get("/dashboard/ota-cancellation-rate")
@cached(ttl=600, key_prefix="dashboard_ota_cancellation")  # Cache for 10 minutes
async def get_ota_cancellation_rate(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    """
    Get OTA cancellation rate - critical revenue KPI
    - Overall cancellation rate
    - By OTA channel
    - By booking window
    - Impact on revenue
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    # Get all bookings in period (created during this period)
    all_bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }):
        all_bookings.append(booking)

    # Separate by status
    total_bookings = len(all_bookings)
    cancelled_bookings = [b for b in all_bookings if b.get('status') == 'cancelled']
    confirmed_bookings = [b for b in all_bookings if b.get('status') in ['confirmed', 'guaranteed', 'checked_in', 'checked_out']]

    # OTA bookings only
    ota_channels = ['booking_com', 'expedia', 'airbnb', 'agoda', 'hotels_com']
    ota_bookings = [b for b in all_bookings if b.get('channel') in ota_channels]
    ota_cancelled = [b for b in ota_bookings if b.get('status') == 'cancelled']

    # Calculate rates
    overall_cancellation_rate = (len(cancelled_bookings) / total_bookings * 100) if total_bookings > 0 else 0
    ota_cancellation_rate = (len(ota_cancelled) / len(ota_bookings) * 100) if len(ota_bookings) > 0 else 0

    # By channel breakdown
    channel_breakdown = {}
    for channel in ota_channels:
        channel_bookings = [b for b in all_bookings if b.get('channel') == channel]
        channel_cancelled = [b for b in channel_bookings if b.get('status') == 'cancelled']

        if channel_bookings:
            channel_breakdown[channel] = {
                'total_bookings': len(channel_bookings),
                'cancelled': len(channel_cancelled),
                'cancellation_rate': round((len(channel_cancelled) / len(channel_bookings) * 100), 1),
                'lost_revenue': sum(b.get('total_amount', 0) for b in channel_cancelled)
            }

    # Booking window analysis (how far in advance was booking made before cancelled)
    cancellation_lead_times = []
    for booking in cancelled_bookings:
        created = datetime.fromisoformat(booking.get('created_at', ''))
        cancelled_at = booking.get('cancelled_at')
        if cancelled_at:
            cancelled_dt = datetime.fromisoformat(cancelled_at) if isinstance(cancelled_at, str) else cancelled_at
            lead_time = (cancelled_dt - created).days
            cancellation_lead_times.append(lead_time)

    avg_lead_time = sum(cancellation_lead_times) / len(cancellation_lead_times) if cancellation_lead_times else 0

    # Revenue impact
    total_lost_revenue = sum(b.get('total_amount', 0) for b in cancelled_bookings)
    ota_lost_revenue = sum(b.get('total_amount', 0) for b in ota_cancelled)
    potential_revenue = sum(b.get('total_amount', 0) for b in all_bookings)

    return {
        'period_days': days,
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'overall': {
            'total_bookings': total_bookings,
            'cancelled_bookings': len(cancelled_bookings),
            'cancellation_rate': round(overall_cancellation_rate, 1),
            'confirmed_bookings': len(confirmed_bookings)
        },
        'ota_performance': {
            'total_ota_bookings': len(ota_bookings),
            'ota_cancelled': len(ota_cancelled),
            'ota_cancellation_rate': round(ota_cancellation_rate, 1),
            'channel_breakdown': channel_breakdown,
            'worst_performing_channel': max(channel_breakdown.items(), key=lambda x: x[1]['cancellation_rate'])[0] if channel_breakdown else None,
            'best_performing_channel': min(channel_breakdown.items(), key=lambda x: x[1]['cancellation_rate'])[0] if channel_breakdown else None
        },
        'cancellation_patterns': {
            'avg_lead_time_days': round(avg_lead_time, 1),
            'same_day_cancellations': sum(1 for lt in cancellation_lead_times if lt == 0),
            'within_24h': sum(1 for lt in cancellation_lead_times if lt <= 1),
            'within_week': sum(1 for lt in cancellation_lead_times if lt <= 7)
        },
        'revenue_impact': {
            'total_lost_revenue': round(total_lost_revenue, 2),
            'ota_lost_revenue': round(ota_lost_revenue, 2),
            'potential_revenue': round(potential_revenue, 2),
            'revenue_retention_rate': round(((potential_revenue - total_lost_revenue) / potential_revenue * 100), 1) if potential_revenue > 0 else 0
        },
        'alerts': [
            f"⚠️ OTA cancellation rate is {'HIGH' if ota_cancellation_rate > 15 else 'NORMAL'}" if ota_cancellation_rate > 15 else "✅ OTA cancellation rate is within normal range",
            f"💰 Lost revenue: ${round(ota_lost_revenue, 2)} from OTA cancellations" if ota_lost_revenue > 0 else None
        ]
    }


# ============= CHECK-IN ENHANCEMENTS =============



@router.get("/dashboard/revenue-expense-chart", dependencies=[Depends(require_op("view_finance_reports"))])
@cached(ttl=600, key_prefix="revenue_expense_chart")  # v63 Bug CY: finance authz hardening
async def get_revenue_expense_chart(
    period: str = "30days",  # 30days, 90days, 12months
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: revenue/expense chart finans
):
    """Get revenue vs expense chart data for dashboard"""
    # Calculate date range based on period
    end = datetime.now(UTC)
    if period == "30days":
        start = end - timedelta(days=30)
        interval = "daily"
    elif period == "90days":
        start = end - timedelta(days=90)
        interval = "weekly"
    else:  # 12months
        start = end - timedelta(days=365)
        interval = "monthly"

    # 2 bagimsiz find paralel — N+1 fix
    charges, expenses = await asyncio.gather(
        db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'voided': False,
            'date': {'$gte': start.isoformat(), '$lte': end.isoformat()},
        }).to_list(10000),
        db.expenses.find({
            'tenant_id': current_user.tenant_id,
            'date': {'$gte': start.isoformat(), '$lte': end.isoformat()},
        }).to_list(10000),
    )

    # Group data by interval
    revenue_data = {}
    expense_data = {}

    for charge in charges:
        date_str = charge.get('date', '')[:10]
        if interval == "daily":
            key = date_str
        elif interval == "weekly":
            week = datetime.fromisoformat(date_str).isocalendar()[1]
            key = f"W{week}"
        else:  # monthly
            key = date_str[:7]  # YYYY-MM

        revenue_data[key] = revenue_data.get(key, 0) + charge.get('total', 0)

    for expense in expenses:
        date_str = expense.get('date', '')[:10]
        if interval == "daily":
            key = date_str
        elif interval == "weekly":
            week = datetime.fromisoformat(date_str).isocalendar()[1]
            key = f"W{week}"
        else:  # monthly
            key = date_str[:7]

        expense_data[key] = expense_data.get(key, 0) + expense.get('amount', 0)

    # Prepare chart data
    all_keys = sorted(set(list(revenue_data.keys()) + list(expense_data.keys())))
    chart_data = []

    for key in all_keys:
        revenue = revenue_data.get(key, 0)
        expense = expense_data.get(key, 0)
        profit = revenue - expense

        chart_data.append({
            'period': key,
            'revenue': round(revenue, 2),
            'expense': round(expense, 2),
            'profit': round(profit, 2),
            'profit_margin': round((profit / revenue * 100), 2) if revenue > 0 else 0
        })

    # Calculate totals
    total_revenue = sum(d['revenue'] for d in chart_data)
    total_expense = sum(d['expense'] for d in chart_data)
    total_profit = total_revenue - total_expense
    avg_profit_margin = round((total_profit / total_revenue * 100), 2) if total_revenue > 0 else 0

    return {
        'period': period,
        'interval': interval,
        'chart_data': chart_data,
        'summary': {
            'total_revenue': round(total_revenue, 2),
            'total_expense': round(total_expense, 2),
            'total_profit': round(total_profit, 2),
            'avg_profit_margin': avg_profit_margin
        }
    }



@router.get("/dashboard/budget-vs-actual", dependencies=[Depends(require_op("view_finance_reports"))])
@cached(ttl=600, key_prefix="budget_vs_actual")  # v63 Bug CY: finance authz hardening
async def get_budget_vs_actual(
    month: str | None = None,  # YYYY-MM format
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: budget vs actual finans
):
    """Get budget vs actual comparison for dashboard"""
    # Default to current month
    if not month:
        month = datetime.now(UTC).strftime('%Y-%m')

    # v63 Bug CZ: UTC-aware datetimes (mongo strings may be aware → naive comparison TypeError)
    start = datetime.fromisoformat(f"{month}-01").replace(tzinfo=UTC)
    # Last day of month
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)

    # v95 — Parallel queries with server-side $sum (was 3 sequential to_list(10000) + Python sum)
    import asyncio as _asyncio
    tid = current_user.tenant_id
    date_range = {'$gte': start.isoformat(), '$lte': end.isoformat()}

    # Charges aggregation: total revenue + room-only revenue in single pipeline
    charges_pipeline = [
        {'$match': {'tenant_id': tid, 'voided': False, 'date': date_range}},
        {'$group': {
            '_id': None,
            'total': {'$sum': {'$ifNull': ['$total', 0]}},
            'room_revenue': {'$sum': {'$cond': [
                {'$eq': ['$charge_category', 'room']},
                {'$ifNull': ['$total', 0]},
                0,
            ]}},
        }},
    ]
    expenses_pipeline = [
        {'$match': {'tenant_id': tid, 'date': date_range}},
        {'$group': {'_id': None, 'total': {'$sum': {'$ifNull': ['$amount', 0]}}}},
    ]

    budget_q = db.budgets.find_one({'tenant_id': tid, 'month': month})
    charges_q = db.folio_charges.aggregate(charges_pipeline).to_list(1)
    expenses_q = db.expenses.aggregate(expenses_pipeline).to_list(1)
    rooms_count_q = db.rooms.count_documents({'tenant_id': tid})
    bookings_q = db.bookings.find(
        {'tenant_id': tid, 'status': {'$in': ['checked_in', 'checked_out']},
         'check_in': date_range},
        {'_id': 0, 'check_in': 1, 'check_out': 1},
    ).to_list(10000)

    budget, charges_agg, expenses_agg, total_rooms, bookings = await _asyncio.gather(
        budget_q, charges_q, expenses_q, rooms_count_q, bookings_q
    )

    # If no budget, create default
    if not budget:
        budget = {
            'revenue_budget': 100000,
            'expense_budget': 70000,
            'occupancy_budget': 75,
            'adr_budget': 150
        }

    actual_revenue = charges_agg[0]['total'] if charges_agg else 0
    room_revenue = charges_agg[0]['room_revenue'] if charges_agg else 0
    actual_expense = expenses_agg[0]['total'] if expenses_agg else 0

    # Get actual occupancy
    days_in_month = (end - start).days + 1
    available_room_nights = total_rooms * days_in_month

    occupied_room_nights = 0
    for booking in bookings:
        # v63 Bug CZ: normalize naive→UTC-aware before comparison
        ci = datetime.fromisoformat(booking['check_in'])
        co = datetime.fromisoformat(booking['check_out'])
        if ci.tzinfo is None: ci = ci.replace(tzinfo=UTC)
        if co.tzinfo is None: co = co.replace(tzinfo=UTC)
        check_in = max(ci, start)
        check_out = min(co, end)
        nights = (check_out - check_in).days
        occupied_room_nights += max(nights, 1)

    actual_occupancy = round((occupied_room_nights / available_room_nights * 100), 2) if available_room_nights > 0 else 0

    # Calculate ADR
    actual_adr = round(room_revenue / occupied_room_nights, 2) if occupied_room_nights > 0 else 0

    # Calculate variances
    revenue_variance = round(((actual_revenue - budget['revenue_budget']) / budget['revenue_budget'] * 100), 2) if budget['revenue_budget'] > 0 else 0
    expense_variance = round(((actual_expense - budget['expense_budget']) / budget['expense_budget'] * 100), 2) if budget['expense_budget'] > 0 else 0
    occupancy_variance = round(actual_occupancy - budget['occupancy_budget'], 2)
    adr_variance = round(((actual_adr - budget['adr_budget']) / budget['adr_budget'] * 100), 2) if budget['adr_budget'] > 0 else 0

    return {
        'month': month,
        'categories': [
            {
                'name': 'Revenue',
                'budget': round(budget['revenue_budget'], 2),
                'actual': round(actual_revenue, 2),
                'variance': revenue_variance,
                'status': 'above' if revenue_variance > 0 else 'below' if revenue_variance < 0 else 'on_target'
            },
            {
                'name': 'Expense',
                'budget': round(budget['expense_budget'], 2),
                'actual': round(actual_expense, 2),
                'variance': expense_variance,
                'status': 'above' if expense_variance > 0 else 'below' if expense_variance < 0 else 'on_target'
            },
            {
                'name': 'Occupancy (%)',
                'budget': budget['occupancy_budget'],
                'actual': actual_occupancy,
                'variance': occupancy_variance,
                'status': 'above' if occupancy_variance > 0 else 'below' if occupancy_variance < 0 else 'on_target'
            },
            {
                'name': 'ADR',
                'budget': round(budget['adr_budget'], 2),
                'actual': actual_adr,
                'variance': adr_variance,
                'status': 'above' if adr_variance > 0 else 'below' if adr_variance < 0 else 'on_target'
            }
        ]
    }



@router.get("/dashboard/monthly-profitability", dependencies=[Depends(require_op("view_finance_reports"))])
@cached(ttl=600, key_prefix="monthly_profitability")  # v63 Bug CY: finance authz hardening
async def get_monthly_profitability(
    months: int = Query(6, ge=1, le=36, description="Last N months (1-36)"),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: monthly profitability finans
):
    """Get monthly profitability for dashboard.

    Single-pass: tüm ay aralığını 2 find çağrısıyla (charges + expenses)
    çekip Python'da takvim ayı bazında gruplar. Önceki sürüm her ay için
    ayrı find atıyordu (2N çağrı = N+1 anti-pattern).

    Ay seçimi: `timedelta(days=30*i)` ay sonu drift yapıyordu (Mart 31'de
    Şubat'ı atlıyordu). Şimdi takvim ayı geriye sayma kullanılır.
    """
    # Takvim ayı geriye sayma (drift-free)
    now = datetime.now(UTC)
    cur_year, cur_month = now.year, now.month

    def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
        """delta ay öne (+) ya da geri (-) kaydır, normalize et."""
        idx = (year * 12 + (month - 1)) + delta
        return idx // 12, (idx % 12) + 1

    # Window başlangıcı: en eski ayın 1'i (geri months-1 ay)
    win_y, win_m = _shift_month(cur_year, cur_month, -(months - 1))
    window_start = datetime(win_y, win_m, 1, tzinfo=UTC)

    # Tek seferde charges + expenses (paralel)
    charges_q = db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'date': {'$gte': window_start.isoformat()},
    }).to_list(100000)
    expenses_q = db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': window_start.isoformat()},
    }).to_list(100000)
    charges, expenses = await asyncio.gather(charges_q, expenses_q)

    def _month_key(date_val) -> str | None:
        """Tarih → 'YYYY-MM'. Padless ISO ('2024-1-15') de tolere eder."""
        if not date_val:
            return None
        try:
            if isinstance(date_val, str):
                # Önce ISO parse dene; başarısızsa ilk 10 char'dan elle çıkar
                try:
                    dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                except ValueError:
                    parts = date_val.split('T', 1)[0].split('-')
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        return f"{int(parts[0]):04d}-{int(parts[1]):02d}"
                    return None
                return dt.strftime('%Y-%m')
            return date_val.strftime('%Y-%m')
        except Exception:
            return None

    revenue_by_month: dict[str, float] = {}
    for c in charges:
        mk = _month_key(c.get('date'))
        if mk:
            revenue_by_month[mk] = revenue_by_month.get(mk, 0.0) + (c.get('total', 0) or 0)

    expense_by_month: dict[str, float] = {}
    for e in expenses:
        mk = _month_key(e.get('date'))
        if mk:
            expense_by_month[mk] = expense_by_month.get(mk, 0.0) + (e.get('amount', 0) or 0)

    profitability_data = []
    # En eskiden bugüne sırayla months ay üret
    for i in range(months):
        y, m = _shift_month(win_y, win_m, i)
        month_str = f"{y:04d}-{m:02d}"
        month_name = datetime(y, m, 1).strftime('%B %Y')
        revenue = revenue_by_month.get(month_str, 0.0)
        expense = expense_by_month.get(month_str, 0.0)
        profit = revenue - expense
        profit_margin = round((profit / revenue * 100), 2) if revenue > 0 else 0

        profitability_data.append({
            'month': month_str,
            'month_name': month_name,
            'revenue': round(revenue, 2),
            'expense': round(expense, 2),
            'profit': round(profit, 2),
            'profit_margin': profit_margin,
        })

    # Calculate averages
    avg_revenue = sum(d['revenue'] for d in profitability_data) / len(profitability_data) if profitability_data else 0
    avg_expense = sum(d['expense'] for d in profitability_data) / len(profitability_data) if profitability_data else 0
    avg_profit = sum(d['profit'] for d in profitability_data) / len(profitability_data) if profitability_data else 0
    avg_profit_margin = sum(d['profit_margin'] for d in profitability_data) / len(profitability_data) if profitability_data else 0

    # Get current month
    current_month = profitability_data[-1] if profitability_data else None

    return {
        'months_data': profitability_data,
        'current_month': current_month,
        'averages': {
            'avg_revenue': round(avg_revenue, 2),
            'avg_expense': round(avg_expense, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_profit_margin': round(avg_profit_margin, 2)
        }
    }



@router.get("/dashboard/trend-kpis")
async def get_trend_kpis(
    period: str = "7days",  # 7days, 30days, 90days
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get trending KPIs with comparison for dashboard"""
    current_user = await get_current_user(credentials)

    # Calculate periods
    days = int(period.replace('days', ''))
    current_end = datetime.now(UTC)
    current_start = current_end - timedelta(days=days)

    previous_end = current_start
    previous_start = previous_end - timedelta(days=days)

    # Helper function to get metrics for a period
    async def get_period_metrics(start, end):
        # Revenue
        charges = await db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'voided': False,
            'date': {
                '$gte': start.isoformat(),
                '$lte': end.isoformat()
            }
        }).to_list(10000)

        revenue = sum(c.get('total', 0) for c in charges)
        room_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'room')

        # Bookings
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'created_at': {
                '$gte': start.isoformat(),
                '$lte': end.isoformat()
            }
        }).to_list(10000)

        bookings_count = len(bookings)

        # Occupancy
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        days_in_period = (end - start).days + 1
        available_room_nights = total_rooms * days_in_period

        occupied_bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['checked_in', 'checked_out']},
            'check_in': {
                '$gte': start.isoformat(),
                '$lte': end.isoformat()
            }
        }).to_list(10000)

        def _parse_dt(val):
            """Güvenli tarih parser: None/eksik/bozuk değerler için None döner."""
            if val is None:
                return None
            try:
                if isinstance(val, str):
                    dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
                elif isinstance(val, datetime):
                    dt = val
                else:
                    return None
            except (ValueError, TypeError):
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt

        occupied_room_nights = 0
        for booking in occupied_bookings:
            ci_raw = booking.get('check_in')
            co_raw = booking.get('check_out')
            ci = _parse_dt(ci_raw)
            co = _parse_dt(co_raw)
            if ci is None or co is None:
                continue
            if co <= ci:
                # Bozuk kayıt (checkout <= checkin) — KPI'yi şişirmemek için atla
                continue
            check_in = max(ci, start)
            check_out = min(co, end)
            nights = (check_out - check_in).days
            if nights <= 0:
                continue
            occupied_room_nights += nights

        occupancy = round((occupied_room_nights / available_room_nights * 100), 2) if available_room_nights > 0 else 0

        # ADR
        adr = round(room_revenue / occupied_room_nights, 2) if occupied_room_nights > 0 else 0

        # RevPAR
        revpar = round(room_revenue / available_room_nights, 2) if available_room_nights > 0 else 0

        # Guest satisfaction (from reviews)
        reviews = await db.reviews.find({
            'tenant_id': current_user.tenant_id,
            'created_at': {
                '$gte': start.isoformat(),
                '$lte': end.isoformat()
            }
        }).to_list(1000)

        avg_rating = sum(r.get('rating', 0) for r in reviews) / len(reviews) if reviews else 0

        return {
            'revenue': revenue,
            'bookings': bookings_count,
            'occupancy': occupancy,
            'adr': adr,
            'revpar': revpar,
            'avg_rating': round(avg_rating, 2)
        }

    current_metrics = await get_period_metrics(current_start, current_end)
    previous_metrics = await get_period_metrics(previous_start, previous_end)

    # Calculate trends
    def calculate_trend(current, previous):
        if previous == 0:
            return 0
        return round(((current - previous) / previous * 100), 2)

    kpis = [
        {
            'name': 'Revenue',
            'current': round(current_metrics['revenue'], 2),
            'previous': round(previous_metrics['revenue'], 2),
            'trend': calculate_trend(current_metrics['revenue'], previous_metrics['revenue']),
            'unit': 'currency',
            'icon': 'dollar'
        },
        {
            'name': 'Bookings',
            'current': current_metrics['bookings'],
            'previous': previous_metrics['bookings'],
            'trend': calculate_trend(current_metrics['bookings'], previous_metrics['bookings']),
            'unit': 'count',
            'icon': 'calendar'
        },
        {
            'name': 'Occupancy',
            'current': current_metrics['occupancy'],
            'previous': previous_metrics['occupancy'],
            'trend': calculate_trend(current_metrics['occupancy'], previous_metrics['occupancy']),
            'unit': 'percentage',
            'icon': 'users'
        },
        {
            'name': 'ADR',
            'current': round(current_metrics['adr'], 2),
            'previous': round(previous_metrics['adr'], 2),
            'trend': calculate_trend(current_metrics['adr'], previous_metrics['adr']),
            'unit': 'currency',
            'icon': 'trending'
        },
        {
            'name': 'RevPAR',
            'current': round(current_metrics['revpar'], 2),
            'previous': round(previous_metrics['revpar'], 2),
            'trend': calculate_trend(current_metrics['revpar'], previous_metrics['revpar']),
            'unit': 'currency',
            'icon': 'chart'
        },
        {
            'name': 'Guest Rating',
            'current': current_metrics['avg_rating'],
            'previous': previous_metrics['avg_rating'],
            'trend': calculate_trend(current_metrics['avg_rating'], previous_metrics['avg_rating']),
            'unit': 'rating',
            'icon': 'star'
        }
    ]

    return {
        'period': period,
        'kpis': kpis
    }

# ===== F&B MODULE ENHANCEMENTS =====



@router.get("/dashboard/gm/anomaly-detection")
@cached(ttl=300, key_prefix="anomaly_detection")  # v95 — 5 min TTL (was uncached → 0.82s every call)
async def get_anomaly_detection(current_user: User = Depends(get_current_user)):
    """Detect anomalies in hotel operations"""
    import asyncio as _asyncio
    try:
        tid = current_user.tenant_id
        # v95 — Parallel projected reads (was 3 sequential to_list(1000) full-doc fetches).
        # Only fields we actually inspect are pulled.
        rooms_task = db.rooms.find(
            {'tenant_id': tid},
            {'_id': 0, 'status': 1}
        ).to_list(2000)
        bookings_task = db.bookings.find(
            {'tenant_id': tid, 'status': {'$in': ['confirmed', 'checked_in']}},
            {'_id': 0, 'status': 1}
        ).to_list(2000)
        # Recent transactions only — anomaly check uses last 10 + overall mean (last 1000 is enough)
        transactions_task = db.transactions.find(
            {'tenant_id': tid},
            {'_id': 0, 'amount': 1}
        ).sort('created_at', -1).limit(1000).to_list(1000)
        maintenance_task = db.maintenance_tasks.find(
            {'tenant_id': tid, 'status': {'$ne': 'completed'}},
            {'_id': 0, 'priority': 1}
        ).to_list(2000)
        rooms, bookings, transactions, maintenance_tasks = await _asyncio.gather(
            rooms_task, bookings_task, transactions_task, maintenance_task
        )

        anomalies = []

        # 1. Check occupancy vs bookings mismatch
        occupied_rooms = len([r for r in rooms if r.get('status') == 'occupied'])
        checked_in_bookings = len([b for b in bookings if b.get('status') == 'checked_in'])

        if abs(occupied_rooms - checked_in_bookings) > 3:
            anomalies.append({
                'type': 'occupancy_mismatch',
                'severity': 'high',
                'title': 'Oda Durumu Uyumsuzluğu',
                'description': f'{occupied_rooms} oda dolu görünüyor ama {checked_in_bookings} aktif check-in var',
                'metric': f'Fark: {abs(occupied_rooms - checked_in_bookings)} oda',
                'detected_at': datetime.utcnow().isoformat()
            })

        # 2. Check for rooms in cleaning for too long
        cleaning_rooms = [r for r in rooms if r.get('status') == 'cleaning']
        if len(cleaning_rooms) > 10:
            anomalies.append({
                'type': 'cleaning_backlog',
                'severity': 'medium',
                'title': 'Temizlik Gecikmesi',
                'description': f'{len(cleaning_rooms)} oda uzun süredir temizleniyor',
                'metric': f'{len(cleaning_rooms)} oda',
                'detected_at': datetime.utcnow().isoformat()
            })

        # 3. Check maintenance tasks (already fetched in parallel block above)
        urgent_tasks = [t for t in maintenance_tasks if t.get('priority') == 'urgent']
        if len(urgent_tasks) > 5:
            anomalies.append({
                'type': 'maintenance_overload',
                'severity': 'high',
                'title': 'Acil Bakım Yoğunluğu',
                'description': f'{len(urgent_tasks)} acil bakım görevi bekliyor',
                'metric': f'{len(urgent_tasks)} acil görev',
                'detected_at': datetime.utcnow().isoformat()
            })

        # 4. Check revenue anomalies (transactions are sorted DESC by created_at, so newest first)
        if transactions:
            avg_transaction = sum(t.get('amount', 0) for t in transactions) / len(transactions)
            recent_transactions = transactions[:10]  # newest 10 (already sorted DESC)

            if recent_transactions:
                recent_avg = sum(t.get('amount', 0) for t in recent_transactions) / len(recent_transactions)

                if recent_avg < avg_transaction * 0.5:
                    anomalies.append({
                        'type': 'revenue_drop',
                        'severity': 'high',
                        'title': 'Gelir Düşüşü',
                        'description': 'Son işlemler ortalamanın %50 altında',
                        'metric': f'Ort: {avg_transaction:.2f}₺ → Son: {recent_avg:.2f}₺',
                        'detected_at': datetime.utcnow().isoformat()
                    })

        # 5. Check for out of order rooms
        oo_rooms = [r for r in rooms if r.get('status') == 'out_of_order']
        if len(oo_rooms) > 0:
            anomalies.append({
                'type': 'out_of_order',
                'severity': 'medium',
                'title': 'Servis Dışı Odalar',
                'description': f'{len(oo_rooms)} oda servis dışı',
                'metric': f'{len(oo_rooms)} oda',
                'detected_at': datetime.utcnow().isoformat()
            })

        return {
            'anomalies': anomalies,
            'total_detected': len(anomalies),
            'scan_time': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.info(f"Anomaly detection error: {str(e)}")
        return {
            'anomalies': [],
            'total_detected': 0,
            'error': str(e)
        }



@router.get("/executive/kpi-snapshot")
@cached(ttl=180, key_prefix="executive_kpi")
async def get_executive_kpi_snapshot(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v71 Bug DH
):
    """
    Get critical KPI snapshot - INSTANT RESPONSE VIA PRE-WARMED CACHE
    """

    # Check pre-warmed cache first (instant!)
    from cache_warmer import cache_warmer
    if cache_warmer:
        cached_data = cache_warmer.get_cached(f"kpi:{current_user.tenant_id}")
        if cached_data:
            return cached_data

    today = datetime.now(UTC).date()
    today_str = today.isoformat()
    tid = current_user.tenant_id
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()

    # Tum bagimsiz sorgular paralel: 2 count + 4 aggregate + 1 list
    (
        total_rooms,
        occupied_rooms,
        revenue_doc,
        bookings_count,
        nps_doc,
        bank_accounts,
        yesterday_revenue_doc,
    ) = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': yesterday}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.bookings.count_documents({
            'tenant_id': tid,
            'status': {'$in': ['checked_in', 'checked_out']},
            'check_in': {'$gte': yesterday},
        }),
        db.reviews.aggregate([
            {'$match': {'tenant_id': tid}},
            {'$group': {'_id': None, 'sum_rating': {'$sum': '$rating'}, 'cnt': {'$sum': 1}}},
        ]).to_list(1),
        db.bank_accounts.find({'tenant_id': tid}).to_list(100),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': two_days_ago, '$lt': yesterday}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
    )

    if total_rooms == 0:
        total_rooms = 50  # Default for empty DB

    occupancy_pct = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
    total_revenue = (revenue_doc[0]['total'] if revenue_doc else 0) or 0

    # Fallback: revenue yoksa booking total_amount'u toplam (tek aggregate)
    if total_revenue == 0:
        fb_doc = await db.bookings.aggregate([
            {'$match': {
                'tenant_id': tid,
                'status': {'$in': ['checked_in', 'checked_out']},
                'check_in': {'$gte': yesterday},
            }},
            {'$group': {'_id': None, 'total': {'$sum': '$total_amount'}}},
        ]).to_list(1)
        total_revenue = (fb_doc[0]['total'] if fb_doc else 0) or 0

    adr = (total_revenue / bookings_count) if bookings_count > 0 else 0
    revpar = (total_revenue / total_rooms) if total_rooms > 0 else 0

    # NPS — aggregate sonucundan
    if nps_doc and nps_doc[0].get('cnt', 0) > 0:
        avg_nps = nps_doc[0]['sum_rating'] / nps_doc[0]['cnt'] * 20
    else:
        avg_nps = 75  # Convert 5-star to 100 scale

    # Cash position
    cash_balance = sum(a.get('balance', 0) for a in bank_accounts)
    if cash_balance == 0:
        cash_balance = total_revenue * 10  # Rough estimate

    yesterday_revenue = (yesterday_revenue_doc[0]['total'] if yesterday_revenue_doc else 0) or 0
    revenue_trend = ((total_revenue - yesterday_revenue) / yesterday_revenue * 100) if yesterday_revenue > 0 else 0

    return {
        'snapshot_date': today_str,
        'snapshot_time': datetime.now(UTC).isoformat(),
        'kpis': {
            'revpar': {
                'value': round(revpar, 2),
                'trend': round(revenue_trend, 1),
                'label': 'RevPAR',
                'currency': '₺'
            },
            'adr': {
                'value': round(adr, 2),
                'trend': round(revenue_trend * 0.8, 1),
                'label': 'ADR',
                'currency': '₺'
            },
            'occupancy': {
                'value': round(occupancy_pct, 1),
                'trend': 2.5,
                'label': 'Doluluk',
                'unit': '%'
            },
            'revenue': {
                'value': round(total_revenue, 2),
                'trend': round(revenue_trend, 1),
                'label': 'Günlük Gelir',
                'currency': '₺'
            },
            'nps': {
                'value': round(avg_nps, 0),
                'trend': 1.2,
                'label': 'NPS Skoru',
                'unit': '/100'
            },
            'cash': {
                'value': round(cash_balance, 2),
                'trend': round(revenue_trend * 0.5, 1),
                'label': 'Nakit Pozisyon',
                'currency': '₺'
            }
        },
        'summary': {
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_rooms,
            'available_rooms': total_rooms - occupied_rooms,
            'bookings_today': bookings_count
        }
    }


# 2. GET /api/executive/performance-alerts - Performance alerts


@router.get("/executive/performance-alerts")
async def get_executive_performance_alerts(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get critical performance alerts for executives
    Revenue drop, low occupancy, cash flow warnings, overbooking risks
    """
    current_user = await get_current_user(credentials)

    alerts = []

    # Revenue drop alert
    today = datetime.now(UTC)
    yesterday = (today - timedelta(days=1)).isoformat()
    last_week = (today - timedelta(days=7)).isoformat()

    # 9 bagimsiz read paralel — N+1 fix.
    # Sum'lar Mongo $sum aggregate ile (silent truncation onlemek icin) — to_list yok.
    month_start = datetime.now(UTC).replace(day=1).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    tid = current_user.tenant_id

    def _sum_pipeline(match: dict, field: str = 'amount') -> list:
        return [{'$match': match}, {'$group': {'_id': None, 't': {'$sum': f'${field}'}}}]

    recent_pay_doc, week_pay_doc, total_rooms, occupied_rooms, arrivals_tomorrow, available_rooms, pending_maintenance, bank_accounts, expense_doc = await asyncio.gather(
        db.payments.aggregate(_sum_pipeline({
            'tenant_id': tid, 'payment_date': {'$gte': yesterday},
        })).to_list(1),
        db.payments.aggregate(_sum_pipeline({
            'tenant_id': tid,
            'payment_date': {'$gte': last_week, '$lt': (today - timedelta(days=6)).isoformat()},
        })).to_list(1),
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_in': tomorrow,
            'status': {'$in': ['confirmed', 'guaranteed']},
        }),
        db.rooms.count_documents({
            'tenant_id': tid, 'status': {'$in': ['available', 'inspected']},
        }),
        db.maintenance_tasks.count_documents({
            'tenant_id': tid, 'status': 'pending',
            'priority': {'$in': ['high', 'urgent']},
        }),
        db.bank_accounts.find({'tenant_id': tid}, {'_id': 0, 'balance': 1}).to_list(1000),
        db.expenses.aggregate(_sum_pipeline({
            'tenant_id': tid, 'expense_date': {'$gte': month_start},
        })).to_list(1),
    )

    recent_revenue = (recent_pay_doc[0]['t'] if recent_pay_doc else 0) or 0
    week_ago_revenue = (week_pay_doc[0]['t'] if week_pay_doc else 0) or 0

    if week_ago_revenue > 0:
        revenue_change = ((recent_revenue - week_ago_revenue) / week_ago_revenue * 100)
        if revenue_change < -10:
            alerts.append({
                'id': str(uuid.uuid4()),
                'type': 'revenue_drop',
                'severity': 'high',
                'title': 'Gelir Düşüşü',
                'message': f'Gelir geçen haftaya göre %{abs(revenue_change):.1f} düştü',
                'value': revenue_change,
                'created_at': datetime.now(UTC).isoformat()
            })

    # Low occupancy alert (above gather'dan geldi)
    if total_rooms > 0:
        occupancy_pct = (occupied_rooms / total_rooms * 100)
        if occupancy_pct < 50:
            alerts.append({
                'id': str(uuid.uuid4()),
                'type': 'low_occupancy',
                'severity': 'medium',
                'title': 'Düşük Doluluk',
                'message': f'Doluluk oranı %{occupancy_pct:.1f} - Hedefin altında',
                'value': occupancy_pct,
                'created_at': datetime.now(UTC).isoformat()
            })

    # Overbooking risk (above gather'dan geldi)
    if arrivals_tomorrow > available_rooms:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'overbooking_risk',
            'severity': 'urgent',
            'title': 'Overbooking Riski',
            'message': f'Yarın {arrivals_tomorrow} giriş var, sadece {available_rooms} oda hazır',
            'value': arrivals_tomorrow - available_rooms,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Maintenance backlog (above gather'dan geldi)
    if pending_maintenance > 5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'maintenance_backlog',
            'severity': 'medium',
            'title': 'Bakım Birikiyor',
            'message': f'{pending_maintenance} acil bakım görevi bekliyor',
            'value': pending_maintenance,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Cash flow warning (bank_accounts find + expense_doc aggregate'tan)
    total_cash = sum(account.get('balance', 0) for account in bank_accounts)
    monthly_costs = (expense_doc[0]['t'] if expense_doc else 0) or 0

    if monthly_costs > 0 and total_cash < monthly_costs * 0.5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'cash_flow_warning',
            'severity': 'high',
            'title': 'Nakit Akışı Uyarısı',
            'message': f'Nakit pozisyon aylık giderlerin %{(total_cash/monthly_costs*100):.0f}\'i seviyesinde',
            'value': total_cash,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Sort by severity
    severity_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    alerts.sort(key=lambda x: severity_order.get(x['severity'], 3))

    return {
        'alerts': alerts,
        'count': len(alerts),
        'urgent_count': len([a for a in alerts if a['severity'] == 'urgent']),
        'high_count': len([a for a in alerts if a['severity'] == 'high'])
    }


# 3. GET /api/executive/daily-summary - Daily summary


@router.get("/executive/comp-set-summary")
async def get_executive_comp_set_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comp-set vs hotel summary for executives (manual/mock comp-set data)."""
    current_user = await get_current_user(credentials)

    # Fetch hotel-level KPIs using existing snapshot logic for consistency
    today = datetime.now(UTC).date().isoformat()

    # 4 bagimsiz read paralel — N+1 fix. Bookings sum Mongo aggregate ile (truncation yok).
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    total_rooms, occupied_rooms, booking_agg, comp_stats = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': current_user.tenant_id}),
        db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'occupied'}),
        db.bookings.aggregate([
            {'$match': {
                'tenant_id': current_user.tenant_id,
                'status': {'$in': ['checked_in', 'checked_out']},
                'check_in': {'$gte': thirty_days_ago},
            }},
            {'$group': {
                '_id': None,
                'rev': {'$sum': {'$ifNull': ['$total_amount', 0]}},
                'nights': {'$sum': {'$max': [1, {'$ifNull': ['$nights', 1]}]}},
            }},
        ]).to_list(1),
        db.comp_set_stats.find(
            {'tenant_id': current_user.tenant_id},
            {'_id': 0},
        ).sort('period_start', -1).limit(1).to_list(1),
    )
    total_rooms = total_rooms or 0
    hotel_occupancy = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0

    total_revenue = (booking_agg[0]['rev'] if booking_agg else 0) or 0
    room_nights = (booking_agg[0]['nights'] if booking_agg else 0) or 0

    hotel_adr = (total_revenue / room_nights) if room_nights > 0 else 0
    hotel_revpar = (total_revenue / (total_rooms * 30)) if total_rooms > 0 else 0

    if comp_stats:
        comp = comp_stats[0]
        comp_occ = comp.get('occupancy', 0)
        comp_adr = comp.get('adr', 0)
        comp_revpar = comp.get('revpar', 0)
    else:
        # Fallback: simple heuristic based on hotel performance
        comp_occ = max(0, min(100, hotel_occupancy * 0.95))
        comp_adr = hotel_adr * 0.97 if hotel_adr else 0
        comp_revpar = hotel_revpar * 0.96 if hotel_revpar else 0

    def safe_index(hotel_val: float, comp_val: float) -> float:
        if comp_val <= 0:
            return 100.0
        return round((hotel_val / comp_val) * 100, 1)

    occ_index = safe_index(hotel_occupancy, comp_occ)
    adr_index = safe_index(hotel_adr, comp_adr)
    revpar_index = safe_index(hotel_revpar, comp_revpar)

    return {
        'period': today,
        'hotel': {
            'occupancy': round(hotel_occupancy, 1),
            'adr': round(hotel_adr, 2),
            'revpar': round(hotel_revpar, 2)
        },
        'comp_set': {
            'occupancy': round(comp_occ, 1),
            'adr': round(comp_adr, 2),
            'revpar': round(comp_revpar, 2)
        },
        'indexes': {
            'occ_index': occ_index,
            'adr_index': adr_index,
            'revpar_index': revpar_index
        }
    }




@router.get("/executive/budget-config")
async def get_executive_budget_config(
    year: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get or initialize budget configuration for a given year (manual input ready)."""
    current_user = await get_current_user(credentials)
    target_year = year or datetime.now(UTC).year

    existing = await db.executive_budgets.find_one(
        {'tenant_id': current_user.tenant_id, 'year': target_year},
        {'_id': 0}
    )
    if existing:
        return existing

    # Default empty config with 12 months
    default_months = [
        {
            'month': m,
            'occ_target': 0.0,
            'adr_target': 0.0,
            'rev_target': 0.0,
        }
        for m in range(1, 13)
    ]

    return {
        'tenant_id': current_user.tenant_id,
        'year': target_year,
        'currency': 'TRY',
        'months': default_months,
    }




@router.put("/executive/budget-config")
async def upsert_executive_budget_config(
    config: BudgetConfig,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_budget_config")),  # v88 DW
):
    """Create or update annual budget configuration for the current tenant."""
    current_user = await get_current_user(credentials)
    doc = config.dict()
    doc['tenant_id'] = current_user.tenant_id

    await db.executive_budgets.update_one(
        {'tenant_id': current_user.tenant_id, 'year': config.year},
        {'$set': doc},
        upsert=True,
    )
    return {'status': 'ok'}




@router.get("/executive/budget-overview")
async def get_executive_budget_overview(
    year: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Return budget vs actual overview for the selected year (simple heuristic actuals)."""
    current_user = await get_current_user(credentials)
    target_year = year or datetime.now(UTC).year

    # Load budget config (or defaults)
    config = await db.executive_budgets.find_one(
        {'tenant_id': current_user.tenant_id, 'year': target_year},
        {'_id': 0}
    )

    if not config:
        # Reuse the same default as get_executive_budget_config
        config = await get_executive_budget_config(year=target_year, credentials=credentials)

    # Compute simple monthly actuals based on bookings
    months_actual = {m: {'rev_actual': 0.0, 'occ_actual': 0.0, 'adr_actual': 0.0} for m in range(1, 13)}

    # Pre-calc total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id}) or 0

    # Fetch bookings for the year
    year_start = datetime(target_year, 1, 1, tzinfo=UTC).isoformat()
    year_end = datetime(target_year + 1, 1, 1, tzinfo=UTC).isoformat()

    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_in', 'checked_out']},
        'check_in': {'$gte': year_start, '$lt': year_end},
    }, {'_id': 0}):
        check_in_str = booking.get('check_in')
        if not check_in_str:
            continue
        try:
            check_in_dt = datetime.fromisoformat(check_in_str)
        except Exception:
            continue
        if check_in_dt.year != target_year:
            continue
        month = check_in_dt.month
        total_amount = float(booking.get('total_amount', 0.0) or 0.0)
        nights = max(1, int(booking.get('nights') or 1))

        ma = months_actual[month]
        ma['rev_actual'] += total_amount
        ma['occ_actual'] += nights

    # Derive ADR and rough occupancy per month
    for m in range(1, 13):
        ma = months_actual[m]
        if ma['occ_actual'] > 0:
            ma['adr_actual'] = ma['rev_actual'] / ma['occ_actual']
        # Rough occupancy: occupied room nights / (total_rooms * days_in_month)
        try:
            days_in_month = (datetime(target_year + (1 if m == 12 else 0), (m % 12) + 1, 1, tzinfo=UTC) - datetime(target_year, m, 1, tzinfo=UTC)).days
        except Exception:
            days_in_month = 30
        if total_rooms > 0 and days_in_month > 0:
            ma['occ_actual'] = (ma['occ_actual'] / (total_rooms * days_in_month)) * 100

    # Merge budget + actuals
    months_output = []
    totals = {
        'rev_target': 0.0,
        'rev_actual': 0.0,
        'occ_target': 0.0,
        'occ_actual': 0.0,
        'adr_target': 0.0,
        'adr_actual': 0.0,
    }

    for month_cfg in config['months']:
        m = month_cfg['month']
        ma = months_actual.get(m, {})
        month_entry = {
            'month': m,
            'occ_target': float(month_cfg.get('occ_target', 0.0)),
            'occ_actual': round(float(ma.get('occ_actual', 0.0)), 1),
            'adr_target': float(month_cfg.get('adr_target', 0.0)),
            'adr_actual': round(float(ma.get('adr_actual', 0.0)), 1),
            'rev_target': float(month_cfg.get('rev_target', 0.0)),
            'rev_actual': round(float(ma.get('rev_actual', 0.0)), 2),
        }
        months_output.append(month_entry)

        totals['rev_target'] += month_entry['rev_target']
        totals['rev_actual'] += month_entry['rev_actual']
        totals['occ_target'] += month_entry['occ_target']
        totals['occ_actual'] += month_entry['occ_actual']
        totals['adr_target'] += month_entry['adr_target']
        totals['adr_actual'] += month_entry['adr_actual']

    def variance_pct(target: float, actual: float) -> float:
        if target == 0:
            return 0.0
        return round(((actual - target) / target) * 100, 1)

    totals_output = {
        'rev_target': round(totals['rev_target'], 2),
        'rev_actual': round(totals['rev_actual'], 2),
        'rev_variance_pct': variance_pct(totals['rev_target'], totals['rev_actual']),
        'occ_target': round(totals['occ_target'] / 12, 1) if totals['occ_target'] else 0.0,
        'occ_actual': round(totals['occ_actual'] / 12, 1) if totals['occ_actual'] else 0.0,
        'adr_target': round(totals['adr_target'] / 12, 1) if totals['adr_target'] else 0.0,
        'adr_actual': round(totals['adr_actual'] / 12, 1) if totals['adr_actual'] else 0.0,
    }

    return {
        'year': target_year,
        'currency': config.get('currency', 'TRY'),
        'months': months_output,
        'totals': totals_output,
    }




@router.get("/executive/daily-summary")
@cached(ttl=180, key_prefix="executive_daily_summary", role_aware=True)
async def get_executive_daily_summary(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get daily summary for executives
    Bookings, revenue, cancellations, complaints, key metrics

    NOT: cache anahtarinin tenant'a duyarli olabilmesi icin
    `current_user`'i Depends ile dogrudan aliyoruz (credentials'tan
    extract edilen tenant cache anahtarina yansimazdi - cross-tenant
    cache sizintisi riski).
    """
    target_date = date if date else datetime.now(UTC).date().isoformat()
    tid = current_user.tenant_id

    # Tum bagimsiz sorgular paralel: 6 count + 1 revenue aggregate
    (
        new_bookings,
        checkins,
        checkouts,
        cancellations,
        revenue_doc,
        complaints,
        incidents,
    ) = await asyncio.gather(
        db.bookings.count_documents({'tenant_id': tid, 'created_at': {'$gte': target_date}}),
        db.bookings.count_documents({'tenant_id': tid, 'check_in': target_date, 'status': 'checked_in'}),
        db.bookings.count_documents({'tenant_id': tid, 'check_out': target_date, 'status': 'checked_out'}),
        db.bookings.count_documents({'tenant_id': tid, 'status': 'cancelled', 'updated_at': {'$gte': target_date}}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': target_date}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.feedback.count_documents({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'created_at': {'$gte': target_date},
        }),
        db.incidents.count_documents({'tenant_id': tid, 'incident_date': target_date}),
    )

    revenue = (revenue_doc[0]['total'] if revenue_doc else 0) or 0

    return {
        'date': target_date,
        'summary': {
            'new_bookings': new_bookings,
            'check_ins': checkins,
            'check_outs': checkouts,
            'cancellations': cancellations,
            'revenue': round(revenue, 2),
            'complaints': complaints,
            'incidents': incidents
        },
        'highlights': {
            'cancellation_rate': round((cancellations / new_bookings * 100) if new_bookings > 0 else 0, 1),
            'avg_revenue_per_booking': round((revenue / checkins) if checkins > 0 else 0, 2)
        }
    }


# ============================================================================
# NOTIFICATION SYSTEM - Push Notifications
# ============================================================================



@router.get("/gm/team-performance")
@router.get("/gm/complaint-management")
async def get_complaint_management(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_system_diagnostics"))  # v103 DX alias drift fix
):
    """
    Get complaint management overview
    Active complaints, categories, resolution times
    """
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)


async def _build_complaint_management(current_user) -> dict:
    """Complaint management ortak helper — 3 feedback find'ı tek gather'da paralel."""
    tid = current_user.tenant_id
    active_docs, all_low_docs, resolved_docs = await asyncio.gather(
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': {'$ne': True},
        }).sort('created_at', -1).limit(20).to_list(20),
        db.feedback.find(
            {'tenant_id': tid, 'rating': {'$lte': 2}},
            {'_id': 0, 'category': 1},
        ).to_list(10000),
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': True,
            'resolved_at': {'$exists': True},
        }).limit(50).to_list(50),
    )

    now_utc = datetime.now(UTC)
    active_complaints = []
    for feedback in active_docs:
        try:
            ca = feedback.get('created_at') or now_utc.isoformat()
            days_open = (now_utc - datetime.fromisoformat(str(ca).replace('Z', '+00:00'))).days
        except Exception:
            days_open = 0
        active_complaints.append({
            'id': feedback.get('id', str(uuid.uuid4())),
            'guest_name': feedback.get('guest_name', 'Anonim'),
            'rating': feedback.get('rating', 1),
            'category': feedback.get('category', 'general'),
            'comment': feedback.get('comment', ''),
            'created_at': feedback.get('created_at'),
            'days_open': days_open,
        })

    categories: dict[str, int] = {}
    for feedback in all_low_docs:
        category = feedback.get('category', 'general')
        categories[category] = categories.get(category, 0) + 1

    category_breakdown = [
        {
            'category': cat,
            'category_tr': {
                'room': 'Oda', 'service': 'Servis', 'cleanliness': 'Temizlik',
                'fnb': 'Yiyecek & İçecek', 'general': 'Genel',
            }.get(cat, cat),
            'count': count,
        }
        for cat, count in categories.items()
    ]

    resolution_hours_list = []
    for feedback in resolved_docs:
        try:
            created = datetime.fromisoformat(feedback['created_at'].replace('Z', '+00:00'))
            resolved = datetime.fromisoformat(feedback['resolved_at'].replace('Z', '+00:00'))
            resolution_hours_list.append((resolved - created).total_seconds() / 3600)
        except Exception:
            continue
    avg_resolution_time = (
        sum(resolution_hours_list) / len(resolution_hours_list)
        if resolution_hours_list else 24
    )

    return {
        'active_complaints': active_complaints,
        'active_count': len(active_complaints),
        'category_breakdown': category_breakdown,
        'avg_resolution_time_hours': round(avg_resolution_time, 1),
        'urgent_complaints': len([c for c in active_complaints if c['days_open'] > 2]),
    }


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode


@router.get("/gm/complaint-management")
async def get_complaint_management_v2(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """v2 — _build_complaint_management helper'ını kullanır (DRY + N+1 fix)."""
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode


@router.get("/gm/snapshot-enhanced")
async def get_enhanced_snapshot(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Enhanced GM snapshot - all critical metrics in one view
    Today vs Yesterday vs Last Week
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    # Get metrics for all three periods
    def get_metrics_for_date(date):
        return {
            'date': date.isoformat(),
            'occupancy': 0,  # To be calculated
            'revenue': 0,
            'check_ins': 0,
            'check_outs': 0,
            'complaints': 0,
            'pending_tasks': 0
        }

    today_metrics = get_metrics_for_date(today)
    yesterday_metrics = get_metrics_for_date(yesterday)
    last_week_metrics = get_metrics_for_date(last_week)

    # 7 bagimsiz read paralel — N+1 fix. Revenue Mongo aggregate ile (truncation yok).
    tid = current_user.tenant_id
    today_iso = today.isoformat()
    total_rooms, occupied_today, payment_agg, check_ins, check_outs, complaints, pending_tasks = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': today_iso}}},
            {'$group': {'_id': None, 't': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_in': today_iso, 'status': 'checked_in',
        }),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_out': today_iso, 'status': 'checked_out',
        }),
        db.feedback.count_documents({
            'tenant_id': tid, 'rating': {'$lte': 2},
            'created_at': {'$gte': today_iso},
        }),
        db.maintenance_tasks.count_documents({
            'tenant_id': tid, 'status': 'pending',
            'priority': {'$in': ['high', 'urgent']},
        }),
    )

    today_metrics['occupancy'] = round((occupied_today / total_rooms * 100) if total_rooms > 0 else 0, 1)
    today_metrics['revenue'] = (payment_agg[0]['t'] if payment_agg else 0) or 0
    today_metrics['check_ins'] = check_ins
    today_metrics['check_outs'] = check_outs
    today_metrics['complaints'] = complaints
    today_metrics['pending_tasks'] = pending_tasks

    # Simulated yesterday and last week data
    yesterday_metrics.update({
        'occupancy': today_metrics['occupancy'] - 3,
        'revenue': today_metrics['revenue'] * 0.95,
        'check_ins': today_metrics['check_ins'] - 2,
        'check_outs': today_metrics['check_outs'] + 1,
        'complaints': today_metrics['complaints'] + 1,
        'pending_tasks': today_metrics['pending_tasks'] + 2
    })

    last_week_metrics.update({
        'occupancy': today_metrics['occupancy'] - 5,
        'revenue': today_metrics['revenue'] * 0.92,
        'check_ins': today_metrics['check_ins'] - 3,
        'check_outs': today_metrics['check_outs'] - 1,
        'complaints': today_metrics['complaints'] + 2,
        'pending_tasks': today_metrics['pending_tasks'] + 3
    })

    return {
        'today': today_metrics,
        'yesterday': yesterday_metrics,
        'last_week': last_week_metrics,
        'trends': {
            'occupancy_trend': 'up' if today_metrics['occupancy'] > yesterday_metrics['occupancy'] else 'down',
            'revenue_trend': 'up' if today_metrics['revenue'] > yesterday_metrics['revenue'] else 'down',
            'complaints_trend': 'up' if today_metrics['complaints'] > yesterday_metrics['complaints'] else 'down'
        }
    }


# ============================================================================
# SALES & CRM MOBILE - Satış & Müşteri Yönetimi
# ============================================================================

# Models

