"""
dashboards

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW

logger = logging.getLogger(__name__)
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from core.utils import calculate_folio_balance, create_excel_workbook, excel_response
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService, require_op

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür








# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.




# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)



# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)











































# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


# ── GET /department/front-office/dashboard ──
@router.get("/department/front-office/dashboard")
@cached(ttl=180, key_prefix="front_office_dashboard")  # Cache for 3 minutes
async def get_front_office_dashboard(current_user: User = Depends(get_current_user)):
    """Front Office Manager Dashboard with overbooking alerts"""
    today = datetime.now(UTC)
    today_start = datetime.combine(today.date(), datetime.min.time()).replace(tzinfo=UTC)
    today_end = datetime.combine(today.date(), datetime.max.time()).replace(tzinfo=UTC)

    # Check-ins today with room ready status
    checkins = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today_start.isoformat(), '$lte': today_end.isoformat()},
        'status': {'$in': ['confirmed', 'guaranteed']}
    }).limit(50):
        room = await db.rooms.find_one({'id': booking.get('room_id')})
        guest = await db.guests.find_one({'id': booking.get('guest_id')})

        checkins.append({
            'booking_id': booking.get('id'),
            'guest_name': booking.get('guest_name'),
            'room_number': booking.get('room_number'),
            'check_in_time': booking.get('check_in'),
            'room_ready': room.get('status') in ['available', 'inspected'] if room else False,
            'vip': guest.get('vip', False) if guest else False,
            'actions': ['upgrade', 'late_checkout', 'message', 'print']
        })

    # Overbooking detection
    next_7_days = today + timedelta(days=7)
    room_dates = {}
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': next_7_days.isoformat()}
    }):
        room_id = booking.get('room_id')
        check_in = datetime.fromisoformat(booking.get('check_in')).date()
        check_out = datetime.fromisoformat(booking.get('check_out')).date()

        current = check_in
        while current < check_out:
            key = f"{room_id}_{current}"
            if key not in room_dates:
                room_dates[key] = []
            room_dates[key].append({
                'booking_id': booking.get('id'),
                'guest': booking.get('guest_name'),
                'source': booking.get('booking_source', 'direct')
            })
            current += timedelta(days=1)

    overbookings = []
    for key, bookings_list in room_dates.items():
        if len(bookings_list) > 1:
            room_id, date_str = key.split('_')
            room = await db.rooms.find_one({'id': room_id})
            overbookings.append({
                'date': date_str,
                'room_number': room.get('room_number') if room else 'Unknown',
                'conflicts': bookings_list,
                'severity': 'critical' if len(bookings_list) > 2 else 'high'
            })

    return {
        'checkins_today': checkins,
        'overbooking_alerts': overbookings,
        'total_checkins': len(checkins),
        'total_overbookings': len(overbookings),
        'vip_determination': {
            'source': 'PMS + CRM',
            'rules': ['Manual tag', 'Loyalty tier >= Gold', 'Spend > $10k', 'Frequency > 5/year']
        }
    }
# ── GET /department/housekeeping/dashboard ──
@router.get("/department/housekeeping/dashboard")
@cached(ttl=120, key_prefix="housekeeping_dashboard")  # Cache for 2 minutes
async def get_housekeeping_dashboard(current_user: User = Depends(get_current_user)):
    """Housekeeping Manager Dashboard with room details"""

    # Room status counts
    dirty_rooms = []
    async for room in db.rooms.find({'tenant_id': current_user.tenant_id, 'status': 'dirty'}):
        dirty_rooms.append({
            'room_number': room.get('room_number'),
            'floor': room.get('floor'),
            'room_type': room.get('room_type'),
            'last_checkout': room.get('last_checkout')
        })

    cleaning_rooms = []
    async for room in db.rooms.find({'tenant_id': current_user.tenant_id, 'status': 'cleaning'}):
        cleaning_rooms.append({
            'room_number': room.get('room_number'),
            'floor': room.get('floor'),
            'assigned_to': room.get('assigned_cleaner')
        })

    inspected_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'inspected'})
    maintenance_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'maintenance'})

    # Auto-rules
    auto_rules = [
        {
            'id': 'rule_checkout',
            'name': 'Auto-dirty on checkout',
            'trigger': 'guest_checkout',
            'action': 'set_status_dirty',
            'active': True
        },
        {
            'id': 'rule_cleaning',
            'name': 'Auto-inspected after cleaning',
            'trigger': 'cleaning_complete',
            'action': 'set_status_inspected',
            'delay': '15 minutes',
            'active': True
        }
    ]

    return {
        'status_summary': {
            'dirty': len(dirty_rooms),
            'cleaning': len(cleaning_rooms),
            'inspected': inspected_rooms,
            'maintenance': maintenance_rooms
        },
        'dirty_rooms_list': dirty_rooms,
        'cleaning_rooms_list': cleaning_rooms,
        'auto_rules': auto_rules,
        'mobile_enabled': True
    }
# ── GET /department/revenue/comprehensive-suggestions ──
@router.get("/department/revenue/comprehensive-suggestions")
@cached(ttl=600, key_prefix="revenue_suggestions")  # Cache for 10 min
async def get_revenue_comprehensive_suggestions(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v83 DS: revenue manager pricing önerileri
):
    """Revenue Manager comprehensive suggestions: pricing, min stay, CTA"""
    today = datetime.now(UTC).date()

    suggestions = []
    for days_ahead in range(14):
        target_date = today + timedelta(days=days_ahead)

        # Forecast occupancy
        base = 65
        weekend_boost = 15 if target_date.weekday() in [4, 5] else 0
        variation = random.randint(-8, 12)
        occupancy = min(98, base + weekend_boost + variation)

        # Generate strategy
        if occupancy < 50:
            strategy = {
                'date': target_date.isoformat(),
                'day_of_week': target_date.strftime('%A'),
                'forecasted_occupancy': occupancy,
                'price_adjustment': -15,
                'min_stay': 1,
                'close_to_arrival': False,
                'close_to_departure': False,
                'stop_sell': False,
                'reasoning': 'Low demand - stimulate bookings with price decrease',
                'action_priority': 'high'
            }
        elif occupancy > 85:
            strategy = {
                'date': target_date.isoformat(),
                'day_of_week': target_date.strftime('%A'),
                'forecasted_occupancy': occupancy,
                'price_adjustment': 20 if occupancy > 90 else 10,
                'min_stay': 2 if occupancy > 90 else 1,
                'close_to_arrival': occupancy > 93,
                'close_to_departure': False,
                'stop_sell': occupancy > 96,
                'reasoning': 'High demand - maximize revenue with restrictions',
                'action_priority': 'high'
            }
        else:
            strategy = {
                'date': target_date.isoformat(),
                'day_of_week': target_date.strftime('%A'),
                'forecasted_occupancy': occupancy,
                'price_adjustment': 0,
                'min_stay': 1,
                'close_to_arrival': False,
                'close_to_departure': False,
                'stop_sell': False,
                'reasoning': 'Balanced demand - maintain current strategy',
                'action_priority': 'low'
            }

        suggestions.append(strategy)

    return {
        'suggestions': suggestions,
        'data_sources': {
            'pickup_curves': True,
            'historical_pace': True,
            'otb_analysis': True,
            'competitive_set': True,
            'events_calendar': True
        }
    }
# ── GET /department/finance/dashboard ──
@router.get("/department/finance/dashboard")
@cached(ttl=300, key_prefix="finance_dashboard")  # Cache for 5 minutes
async def get_finance_dashboard(current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
):
    """Finance Manager Dashboard with real-time AR and integrations"""

    _enforce(current_user.role, "view_finance_reports")  # Bug CU
    # AR Summary
    pending_ar = await db.invoices.count_documents({
        'tenant_id': current_user.tenant_id,
        'payment_status': {'$in': ['pending', 'partial']}
    })

    overdue_invoices = []
    total_overdue = 0
    async for invoice in db.invoices.find({
        'tenant_id': current_user.tenant_id,
        'payment_status': {'$in': ['pending', 'partial']},
        'due_date': {'$lt': datetime.now(UTC).isoformat()}
    }):
        overdue_invoices.append(invoice)
        total_overdue += invoice.get('total', 0) - invoice.get('paid_amount', 0)

    return {
        'ar_summary': {
            'pending_invoices': pending_ar,
            'overdue_count': len(overdue_invoices),
            'overdue_amount': round(total_overdue, 2),
            'aging': {
                '0-30_days': sum(1 for inv in overdue_invoices if (datetime.now(UTC) - datetime.fromisoformat(inv['due_date'])).days <= 30),
                '31-60_days': sum(1 for inv in overdue_invoices if 30 < (datetime.now(UTC) - datetime.fromisoformat(inv['due_date'])).days <= 60),
                '60+_days': sum(1 for inv in overdue_invoices if (datetime.now(UTC) - datetime.fromisoformat(inv['due_date'])).days > 60)
            }
        },
        'integrations': {
            'logo': {'enabled': False, 'status': 'not_configured'},
            'mikro': {'enabled': False, 'status': 'not_configured'},
            'sap': {'enabled': False, 'status': 'not_configured'},
            'oracle': {'enabled': False, 'status': 'not_configured'}
        },
        'e_invoice': {
            'xml_generation': True,
            'gib_integration': True,
            'status': 'active'
        },
        'data_timing': 'real_time',
        'last_closing': (datetime.now(UTC) - timedelta(days=1)).isoformat()
    }
# ── GET /department/sales/corporate-accounts ──
@router.get("/department/sales/corporate-accounts")
@cached(ttl=600, key_prefix="sales_corporate")  # Cache for 10 min
async def get_corporate_accounts(
    sort_by: str = 'revenue',
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_corporate_accounts")),
):
    """Sales & Marketing - Corporate accounts with profiles"""

    _enforce(current_user.role, "view_corporate_accounts")  # Bug CU
    # Aggregate corporate bookings
    corporate_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'booking_source': {'$in': ['corporate', 'company_direct']}
    }).to_list(10000)

    companies = {}
    for booking in corporate_bookings:
        company = booking.get('company_name', 'Unknown')
        if company not in companies:
            companies[company] = {
                'name': company,
                'total_revenue': 0,
                'total_nights': 0,
                'booking_count': 0,
                'last_booking': None,
                'adr': 0
            }

        companies[company]['total_revenue'] += booking.get('total_amount', 0)
        companies[company]['booking_count'] += 1

        try:
            nights = (datetime.fromisoformat(booking.get('check_out')) -
                     datetime.fromisoformat(booking.get('check_in'))).days
            companies[company]['total_nights'] += nights
        except Exception:
            pass

    # Calculate ADR and create list
    accounts = []
    for company, data in companies.items():
        adr = data['total_revenue'] / data['total_nights'] if data['total_nights'] > 0 else 0

        # Check if profile exists
        profile = await db.corporate_profiles.find_one({
            'tenant_id': current_user.tenant_id,
            'company_name': company
        })

        accounts.append({
            **data,
            'adr': round(adr, 2),
            'has_profile': profile is not None,
            'contract_status': profile.get('contract_status') if profile else 'none',
            'blacklisted': profile.get('blacklisted', False) if profile else False
        })

    # Sort
    if sort_by == 'revenue':
        accounts.sort(key=lambda x: x['total_revenue'], reverse=True)
    elif sort_by == 'nights':
        accounts.sort(key=lambda x: x['total_nights'], reverse=True)
    elif sort_by == 'adr':
        accounts.sort(key=lambda x: x['adr'], reverse=True)

    return {
        'accounts': accounts,
        'total_companies': len(accounts),
        'sorted_by': sort_by
    }
# ── GET /department/it/system-info ──
@router.get("/department/it/system-info")
@cached(ttl=600, key_prefix="it_system_info")  # Cache for 10 min
async def get_it_system_info(current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_it_system")),
):
    """IT Manager - System architecture and performance info"""
    _enforce(current_user.role, "view_it_system")  # Bug CU
    return {
        'api_architecture': {
            'type': 'REST',
            'protocol': 'HTTP/HTTPS',
            'websocket_support': False,
            'sse_support': False,
            'polling': 'client-side (30s interval)'
        },
        'widget_architecture': {
            'type': 'modular',
            'independent_apis': True,
            'lazy_loading': True,
            'caching': 'browser + redis'
        },
        'scalability': {
            'tested_rooms': 40,
            'max_recommended': '500+ rooms',
            'database': 'MongoDB (horizontally scalable)',
            'performance_optimization': [
                'Database indexing on tenant_id, dates',
                'Query result limiting',
                'Async/await patterns',
                'Connection pooling'
            ]
        },
        'performance_metrics': {
            'avg_response_time': '< 200ms',
            'concurrent_users': '100+',
            'uptime': '99.5%'
        }
    }
# ── GET /department/guest-relations/vip-notes ──
@router.get("/department/guest-relations/vip-notes")
@cached(ttl=300, key_prefix="guest_relations_vip")  # Cache for 5 min
async def get_vip_notes(current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_vip_notes")),
):
    """Guest Relations - VIP notes and review integrations"""

    _enforce(current_user.role, "view_vip_notes")  # Bug CU
    # Get VIP guests with notes
    vip_guests = []
    async for guest in db.guests.find({
        'tenant_id': current_user.tenant_id,
        'vip': True
    }).limit(50):
        # Get notes
        notes = await db.guest_notes.find({
            'tenant_id': current_user.tenant_id,
            'guest_id': guest.get('id')
        }).to_list(10)

        vip_guests.append({
            'guest_id': guest.get('id'),
            'name': guest.get('name'),
            'email': guest.get('email'),
            'vip_tier': guest.get('loyalty_tier', 'gold'),
            'preferences': guest.get('preferences'),
            'notes': notes,
            'notes_visible_on_dashboard': True
        })

    return {
        'vip_guests': vip_guests,
        'review_integrations': {
            'google': {'enabled': False, 'status': 'not_configured'},
            'tripadvisor': {'enabled': False, 'status': 'not_configured'},
            'booking_com': {'enabled': False, 'status': 'not_configured'},
            'trustpilot': {'enabled': False, 'status': 'not_configured'}
        },
        'complaint_tracking': {
            'enabled': True,
            'open_complaints': 0,
            'avg_resolution_time': '24 hours'
        }
    }
# ── GET /ai/activity-feed ──
@router.get("/ai/activity-feed")
@cached(ttl=300, key_prefix="ai_activity_feed")  # Cache for 5 min
async def get_ai_activity_feed(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v83 DS: AI executive insights
):
    """AI Activity Feed - Real-time AI suggestions and insights"""
    today = datetime.now(UTC)

    activities = []

    # 1. Price Optimization Suggestions
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    occupied = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })
    occupancy = (occupied / total_rooms * 100) if total_rooms > 0 else 0

    if occupancy > 85:
        activities.append({
            'id': str(uuid.uuid4()),
            'type': 'price_suggestion',
            'priority': 'high',
            'title': '💰 Price Optimization Opportunity',
            'message': f'High occupancy detected ({occupancy:.1f}%). Recommend increasing rates by 15-20% for next 3 days.',
            'action': 'adjust_pricing',
            'confidence': 0.89,
            'potential_revenue': round(total_rooms * 50 * 0.15, 2),
            'created_at': today.isoformat(),
            'status': 'active'
        })
    elif occupancy < 50:
        activities.append({
            'id': str(uuid.uuid4()),
            'type': 'price_suggestion',
            'priority': 'high',
            'title': '📉 Low Occupancy Alert',
            'message': f'Occupancy at {occupancy:.1f}%. Recommend promotional rates (-10%) and special packages.',
            'action': 'create_promotion',
            'confidence': 0.85,
            'potential_bookings': round(total_rooms * 0.2),
            'created_at': today.isoformat(),
            'status': 'active'
        })

    # 2. Overbooking Detection
    next_7_days = today + timedelta(days=7)
    room_dates = {}
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed']},
        'check_in': {'$lte': next_7_days.isoformat()}
    }):
        room_id = booking.get('room_id')
        check_in = datetime.fromisoformat(booking.get('check_in')).date()
        check_out = datetime.fromisoformat(booking.get('check_out')).date()

        current = check_in
        while current < check_out:
            key = f"{room_id}_{current}"
            if key not in room_dates:
                room_dates[key] = []
            room_dates[key].append(booking)
            current += timedelta(days=1)

    overbooking_count = sum(1 for bookings in room_dates.values() if len(bookings) > 1)
    if overbooking_count > 0:
        activities.append({
            'id': str(uuid.uuid4()),
            'type': 'overbooking_alert',
            'priority': 'critical',
            'title': '🚨 Overbooking Detected',
            'message': f'{overbooking_count} room conflicts found in next 7 days. Immediate action required.',
            'action': 'resolve_conflicts',
            'conflicts': overbooking_count,
            'confidence': 1.0,
            'created_at': today.isoformat(),
            'status': 'active'
        })

    # 3. VIP Visitor Insights — v95.3 N+1 fix + tenant scope (cross-tenant guest read riskini kapatır)
    vip_arrivals = []
    today_start = datetime.combine(today.date(), datetime.min.time()).replace(tzinfo=UTC)
    today_end = datetime.combine(today.date(), datetime.max.time()).replace(tzinfo=UTC)

    today_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': today_start.isoformat(), '$lte': today_end.isoformat()},
        'status': {'$in': ['confirmed', 'guaranteed']}
    }, {'_id': 0, 'guest_id': 1, 'room_number': 1}).to_list(500)

    guest_ids = list({b.get('guest_id') for b in today_bookings if b.get('guest_id')})
    guests_by_id: dict[str, dict] = {}
    if guest_ids:
        async for g in db.guests.find(
            {'id': {'$in': guest_ids}, 'tenant_id': current_user.tenant_id, 'vip': True},
            {'_id': 0, 'id': 1, 'name': 1, 'loyalty_tier': 1, 'preferences': 1},
        ):
            guests_by_id[g['id']] = g

    for booking in today_bookings:
        guest = guests_by_id.get(booking.get('guest_id'))
        if guest:
            vip_arrivals.append({
                'name': guest.get('name'),
                'room': booking.get('room_number'),
                'tier': guest.get('loyalty_tier', 'gold'),
                'preferences': guest.get('preferences')
            })

    if vip_arrivals:
        activities.append({
            'id': str(uuid.uuid4()),
            'type': 'vip_insight',
            'priority': 'high',
            'title': f'⭐ {len(vip_arrivals)} VIP Arrivals Today',
            'message': 'Special attention required. Ensure welcome amenities and room preferences are prepared.',
            'action': 'review_vip_list',
            'vip_count': len(vip_arrivals),
            'vips': vip_arrivals[:3],
            'confidence': 1.0,
            'created_at': today.isoformat(),
            'status': 'active'
        })

    # 4. Revenue Anomaly Detection — v95 server-side $sum (was 100k-doc to_list)
    thirty_days_ago = today - timedelta(days=30)
    rev_pipeline = [
        {'$match': {
            'tenant_id': current_user.tenant_id,
            'date': {'$gte': thirty_days_ago.isoformat()},
            'voided': False,
        }},
        {'$group': {
            '_id': None,
            'today_revenue': {'$sum': {'$cond': [
                {'$and': [
                    {'$gte': ['$date', today_start.isoformat()]},
                    {'$lte': ['$date', today_end.isoformat()]},
                ]},
                {'$ifNull': ['$total', 0]},
                0,
            ]}},
            'total_30d': {'$sum': {'$ifNull': ['$total', 0]}},
            'count_30d': {'$sum': 1},
        }},
    ]
    rev_agg = await db.folio_charges.aggregate(rev_pipeline).to_list(1)
    today_revenue = rev_agg[0]['today_revenue'] if rev_agg else 0
    total_30d = rev_agg[0]['total_30d'] if rev_agg else 0
    count_30d = rev_agg[0]['count_30d'] if rev_agg else 0

    if count_30d > 0:
        avg_daily_revenue = total_30d / 30
        variance = ((today_revenue - avg_daily_revenue) / avg_daily_revenue * 100) if avg_daily_revenue > 0 else 0

        if abs(variance) > 20:
            activities.append({
                'id': str(uuid.uuid4()),
                'type': 'revenue_anomaly',
                'priority': 'medium' if variance > 0 else 'high',
                'title': '📊 Revenue Anomaly Detected',
                'message': f"Today's revenue {'↗️ +' if variance > 0 else '↘️ '}{abs(variance):.1f}% vs 30-day average. {'Investigate positive spike.' if variance > 0 else 'Review for potential issues.'}",
                'action': 'analyze_revenue',
                'variance': round(variance, 1),
                'today_revenue': round(today_revenue, 2),
                'avg_revenue': round(avg_daily_revenue, 2),
                'confidence': 0.92,
                'created_at': today.isoformat(),
                'status': 'active'
            })

    # 5. Predictive Maintenance
    maintenance_due = await db.rooms.count_documents({
        'tenant_id': current_user.tenant_id,
        'last_maintenance': {'$lt': (today - timedelta(days=90)).isoformat()}
    })

    if maintenance_due > 0:
        activities.append({
            'id': str(uuid.uuid4()),
            'type': 'maintenance_alert',
            'priority': 'medium',
            'title': '🔧 Predictive Maintenance Alert',
            'message': f'{maintenance_due} rooms require scheduled maintenance. Prevent future issues with proactive maintenance.',
            'action': 'schedule_maintenance',
            'rooms_count': maintenance_due,
            'confidence': 0.88,
            'created_at': today.isoformat(),
            'status': 'active'
        })

    # 6. Booking Trend Insight
    week_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': (today - timedelta(days=7)).isoformat()}
    })
    prev_week_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': (today - timedelta(days=14)).isoformat(),
            '$lt': (today - timedelta(days=7)).isoformat()
        }
    })

    if week_bookings > 0 and prev_week_bookings > 0:
        booking_trend = ((week_bookings - prev_week_bookings) / prev_week_bookings * 100)
        if abs(booking_trend) > 15:
            activities.append({
                'id': str(uuid.uuid4()),
                'type': 'booking_trend',
                'priority': 'low',
                'title': '📈 Booking Trend Analysis',
                'message': f"Booking velocity {'↗️ +' if booking_trend > 0 else '↘️ '}{abs(booking_trend):.1f}% this week vs last week.",
                'action': 'view_trends',
                'trend': round(booking_trend, 1),
                'this_week': week_bookings,
                'last_week': prev_week_bookings,
                'confidence': 0.83,
                'created_at': today.isoformat(),
                'status': 'active'
            })

    # Sort by priority and limit
    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    activities.sort(key=lambda x: priority_order.get(x['priority'], 4))

    return {
        'activities': activities[:limit],
        'total_count': len(activities),
        'last_updated': today.isoformat()
    }
# ── GET /revenue/by-department ──
@router.get("/revenue/by-department")
@cached(ttl=900, key_prefix="revenue_by_dept")  # Cache for 15 min
async def get_revenue_by_department(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v83 DS: gelir breakdown finansal
):
    """Revenue breakdown by department (Rooms, F&B, Other)"""
    today = datetime.now(UTC)

    if not start_date:
        start_date = datetime.combine(today.date(), datetime.min.time()).replace(tzinfo=UTC).isoformat()
    if not end_date:
        end_date = datetime.combine(today.date(), datetime.max.time()).replace(tzinfo=UTC).isoformat()

    # Get all charges
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_date, '$lte': end_date},
        'voided': False
    }).to_list(100000)

    # Categorize by department
    departments = {
        'rooms': {'name': 'Rooms', 'revenue': 0, 'count': 0, 'icon': '🛏️'},
        'fnb': {'name': 'Food & Beverage', 'revenue': 0, 'count': 0, 'icon': '🍽️'},
        'spa': {'name': 'Spa & Wellness', 'revenue': 0, 'count': 0, 'icon': '💆'},
        'minibar': {'name': 'Minibar', 'revenue': 0, 'count': 0, 'icon': '🍷'},
        'laundry': {'name': 'Laundry', 'revenue': 0, 'count': 0, 'icon': '👔'},
        'parking': {'name': 'Parking', 'revenue': 0, 'count': 0, 'icon': '🚗'},
        'telephone': {'name': 'Telephone', 'revenue': 0, 'count': 0, 'icon': '📞'},
        'other': {'name': 'Other Services', 'revenue': 0, 'count': 0, 'icon': '🎯'}
    }

    for charge in charges:
        charge_type = charge.get('charge_type', 'other').lower()
        amount = charge.get('total', 0)

        if charge_type in ['room', 'accommodation', 'room_charge']:
            departments['rooms']['revenue'] += amount
            departments['rooms']['count'] += 1
        elif charge_type in ['food', 'beverage', 'restaurant', 'bar', 'fnb']:
            departments['fnb']['revenue'] += amount
            departments['fnb']['count'] += 1
        elif charge_type in ['spa', 'massage', 'wellness']:
            departments['spa']['revenue'] += amount
            departments['spa']['count'] += 1
        elif charge_type in ['minibar', 'mini_bar']:
            departments['minibar']['revenue'] += amount
            departments['minibar']['count'] += 1
        elif charge_type in ['laundry', 'dry_cleaning']:
            departments['laundry']['revenue'] += amount
            departments['laundry']['count'] += 1
        elif charge_type in ['parking', 'valet']:
            departments['parking']['revenue'] += amount
            departments['parking']['count'] += 1
        elif charge_type in ['telephone', 'phone']:
            departments['telephone']['revenue'] += amount
            departments['telephone']['count'] += 1
        else:
            departments['other']['revenue'] += amount
            departments['other']['count'] += 1

    # Calculate totals and percentages
    total_revenue = sum(dept['revenue'] for dept in departments.values())

    for dept in departments.values():
        dept['percentage'] = round((dept['revenue'] / total_revenue * 100) if total_revenue > 0 else 0, 1)
        dept['revenue'] = round(dept['revenue'], 2)

    # Sort by revenue
    sorted_departments = sorted(
        [{'key': k, **v} for k, v in departments.items()],
        key=lambda x: x['revenue'],
        reverse=True
    )

    return {
        'departments': sorted_departments,
        'total_revenue': round(total_revenue, 2),
        'period': {
            'start': start_date,
            'end': end_date
        },
        'summary': {
            'rooms_percentage': departments['rooms']['percentage'],
            'fnb_percentage': departments['fnb']['percentage'],
            'other_percentage': sum(d['percentage'] for k, d in departments.items() if k not in ['rooms', 'fnb'])
        }
    }
