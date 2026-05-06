"""
dashboard_core

Auto-split sub-router (shared imports/classes inlined).
"""
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
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
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

















# ============= CHECK-IN ENHANCEMENTS =============













# ===== F&B MODULE ENHANCEMENTS =====








# 2. GET /api/executive/performance-alerts - Performance alerts




# 3. GET /api/executive/daily-summary - Daily summary




















# ============================================================================
# NOTIFICATION SYSTEM - Push Notifications
# ============================================================================





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




# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode




# ============================================================================
# SALES & CRM MOBILE - Satış & Müşteri Yönetimi
# ============================================================================

# Models

router = APIRouter(prefix="/api", tags=["PMS / Dashboard"])


# ── GET /dashboard/role-based ──
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
        from core.guest_name_utils import display_guest_name
        vip_arrivals = []
        for booking in candidate_bookings:
            guest = guests_by_id.get(booking.get('guest_id'))
            if guest:
                vip_arrivals.append({
                    'guest_name': display_guest_name(guest.get('name'), booking.get('guest_id')),
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
        }, {'_id': 0, 'id': 1, 'guest_name': 1, 'guest_id': 1, 'room_number': 1, 'check_in': 1, 'status': 1, 'room_id': 1}).limit(20).to_list(length=20)
        room_ids = [b.get('room_id') for b in fd_bookings if b.get('room_id')]
        rooms_by_id = {}
        if room_ids:
            async for r in db.rooms.find(
                {'id': {'$in': room_ids}, 'tenant_id': current_user.tenant_id},
                {'_id': 0, 'id': 1, 'status': 1},
            ):
                rooms_by_id[r['id']] = r
        from core.guest_name_utils import display_guest_name
        arrivals = []
        for booking in fd_bookings:
            room = rooms_by_id.get(booking.get('room_id'))
            arrivals.append({
                'id': booking.get('id'),
                'guest_name': display_guest_name(booking.get('guest_name'), booking.get('guest_id')),
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
# ── GET /dashboard/gm-forecast ──
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
# ── GET /dashboard/employee-performance ──
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
# ── GET /dashboard/guest-satisfaction-trends ──
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
# ── GET /dashboard/ota-cancellation-rate ──
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
# ── GET /dashboard/revenue-expense-chart ──
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
# ── GET /dashboard/budget-vs-actual ──
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
# ── GET /dashboard/monthly-profitability ──
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
# ── GET /dashboard/trend-kpis ──
@router.get("/dashboard/trend-kpis")
@cached(ttl=300, key_prefix="trend_kpis")  # v96 — 5 min cache
async def get_trend_kpis(
    period: str = "7days",  # 7days, 30days, 90days
    current_user: User = Depends(get_current_user)
):
    """Get trending KPIs with comparison for dashboard.

    v96 perf:
      - DB-side $sum/$avg via aggregate (no full-doc fetch + Python sum)
      - count_documents for booking count (no doc materialization)
      - asyncio.gather for both periods + intra-period parallel queries
      - rooms count fetched once, reused across periods
      - 5 min cache decorator
    """
    import asyncio as _asyncio

    days = int(period.replace('days', ''))
    current_end = datetime.now(UTC)
    current_start = current_end - timedelta(days=days)
    previous_end = current_start
    previous_start = previous_end - timedelta(days=days)

    tid = current_user.tenant_id

    def _parse_dt(val):
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

    async def _revenue_agg(start, end):
        """DB-side sum: total + room_revenue in one aggregate."""
        pipeline = [
            {'$match': {
                'tenant_id': tid,
                'voided': False,
                'date': {'$gte': start.isoformat(), '$lte': end.isoformat()}
            }},
            {'$group': {
                '_id': None,
                'revenue': {'$sum': '$total'},
                'room_revenue': {'$sum': {
                    '$cond': [{'$eq': ['$charge_category', 'room']}, '$total', 0]
                }}
            }}
        ]
        cur = db.folio_charges.aggregate(pipeline)
        rows = await cur.to_list(1)
        if rows:
            return rows[0].get('revenue', 0) or 0, rows[0].get('room_revenue', 0) or 0
        return 0, 0

    async def _rating_agg(start, end):
        pipeline = [
            {'$match': {
                'tenant_id': tid,
                'created_at': {'$gte': start.isoformat(), '$lte': end.isoformat()}
            }},
            {'$group': {'_id': None, 'avg': {'$avg': '$rating'}}}
        ]
        rows = await db.reviews.aggregate(pipeline).to_list(1)
        if rows and rows[0].get('avg') is not None:
            return float(rows[0]['avg'])
        return 0.0

    async def _occupied_nights(start, end):
        """Project only check_in/check_out — minimize bandwidth."""
        cur = db.bookings.find(
            {
                'tenant_id': tid,
                'status': {'$in': ['checked_in', 'checked_out']},
                'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}
            },
            {'_id': 0, 'check_in': 1, 'check_out': 1}
        )
        nights = 0
        async for b in cur:
            ci = _parse_dt(b.get('check_in'))
            co = _parse_dt(b.get('check_out'))
            if ci is None or co is None or co <= ci:
                continue
            check_in = max(ci, start)
            check_out = min(co, end)
            n = (check_out - check_in).days
            if n > 0:
                nights += n
        return nights

    async def get_period_metrics(start, end, total_rooms):
        rev_task = _revenue_agg(start, end)
        bookings_task = db.bookings.count_documents({
            'tenant_id': tid,
            'created_at': {'$gte': start.isoformat(), '$lte': end.isoformat()}
        })
        occ_task = _occupied_nights(start, end)
        rating_task = _rating_agg(start, end)

        (revenue, room_revenue), bookings_count, occupied_room_nights, avg_rating = \
            await _asyncio.gather(rev_task, bookings_task, occ_task, rating_task)

        days_in_period = (end - start).days + 1
        available_room_nights = total_rooms * days_in_period

        occupancy = round((occupied_room_nights / available_room_nights * 100), 2) if available_room_nights > 0 else 0
        adr = round(room_revenue / occupied_room_nights, 2) if occupied_room_nights > 0 else 0
        revpar = round(room_revenue / available_room_nights, 2) if available_room_nights > 0 else 0

        return {
            'revenue': revenue,
            'bookings': bookings_count,
            'occupancy': occupancy,
            'adr': adr,
            'revpar': revpar,
            'avg_rating': round(avg_rating, 2)
        }

    # rooms count is tenant-wide — fetch once
    total_rooms = await db.rooms.count_documents({'tenant_id': tid})

    # Run both periods in parallel
    current_metrics, previous_metrics = await _asyncio.gather(
        get_period_metrics(current_start, current_end, total_rooms),
        get_period_metrics(previous_start, previous_end, total_rooms),
    )

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
# ── GET /dashboard/gm/anomaly-detection ──
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
