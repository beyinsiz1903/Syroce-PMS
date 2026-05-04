"""
maintenance

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_module as require_module_rbac  # v89 DW
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel











































_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /maintenance/reports/weekly ──
@router.get("/maintenance/reports/weekly")
async def get_weekly_maintenance_report(
    week_offset: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get weekly maintenance report"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
    week_end = week_start + timedelta(days=6)

    # Get all maintenance tasks for the week
    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        }
    }

    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop('_id', None)
        all_tasks.append(task)

    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get('status') == 'completed'])
    in_progress_tasks = len([t for t in all_tasks if t.get('status') == 'in_progress'])
    pending_tasks = len([t for t in all_tasks if t.get('status') == 'pending'])
    emergency_tasks = len([t for t in all_tasks if t.get('priority') == 'emergency'])

    # Calculate SLA compliance
    sla_compliant = 0
    for task in all_tasks:
        if task.get('status') == 'completed' and task.get('sla_met'):
            sla_compliant += 1

    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)
    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)

    # Calculate average response time
    response_times = [t.get('response_time_minutes', 0) for t in all_tasks if t.get('response_time_minutes')]
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0

    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get('category', 'other')
        if category not in by_category:
            by_category[category] = {'count': 0, 'completed': 0}
        by_category[category]['count'] += 1
        if task.get('status') == 'completed':
            by_category[category]['completed'] += 1

    # Group by priority
    by_priority = {
        'emergency': len([t for t in all_tasks if t.get('priority') == 'emergency']),
        'high': len([t for t in all_tasks if t.get('priority') == 'high']),
        'normal': len([t for t in all_tasks if t.get('priority') == 'normal']),
        'low': len([t for t in all_tasks if t.get('priority') == 'low'])
    }

    # Top issues
    issue_counts = {}
    for task in all_tasks:
        issue = task.get('issue_type', 'Other')
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        'period': {
            'start': week_start.date().isoformat(),
            'end': week_end.date().isoformat(),
            'week_number': week_start.isocalendar()[1]
        },
        'summary': {
            'total_tasks': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'emergency': emergency_tasks,
            'completion_rate': completion_rate,
            'sla_compliance': sla_compliance_rate,
            'avg_response_time': avg_response_time
        },
        'by_category': by_category,
        'by_priority': by_priority,
        'top_issues': [{'issue': issue, 'count': count} for issue, count in top_issues],
        'tasks': all_tasks[:10]  # Latest 10 tasks
    }
# ── GET /maintenance/reports/monthly ──
@router.get("/maintenance/reports/monthly")
async def get_monthly_maintenance_report(
    month: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get monthly maintenance report"""
    current_user = await get_current_user(credentials)

    if not month:
        month = datetime.now(UTC).strftime('%Y-%m')

    year, m = month.split('-')
    month_start = datetime(int(year), int(m), 1, tzinfo=UTC)

    # Calculate month end
    if int(m) == 12:
        month_end = datetime(int(year) + 1, 1, 1, tzinfo=UTC) - timedelta(days=1)
    else:
        month_end = datetime(int(year), int(m) + 1, 1, tzinfo=UTC) - timedelta(days=1)

    # Get all maintenance tasks for the month
    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': month_start.isoformat(),
            '$lte': month_end.isoformat()
        }
    }

    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop('_id', None)
        all_tasks.append(task)

    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get('status') == 'completed'])
    in_progress_tasks = len([t for t in all_tasks if t.get('status') == 'in_progress'])
    pending_tasks = len([t for t in all_tasks if t.get('status') == 'pending'])
    cancelled_tasks = len([t for t in all_tasks if t.get('status') == 'cancelled'])

    # Calculate costs
    total_cost = sum(t.get('cost', 0) for t in all_tasks if t.get('cost'))
    parts_cost = sum(t.get('parts_cost', 0) for t in all_tasks if t.get('parts_cost'))
    labor_cost = sum(t.get('labor_cost', 0) for t in all_tasks if t.get('labor_cost'))

    # Calculate times
    response_times = [t.get('response_time_minutes', 0) for t in all_tasks if t.get('response_time_minutes')]
    resolution_times = [t.get('resolution_time_minutes', 0) for t in all_tasks if t.get('resolution_time_minutes')]

    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0
    avg_resolution_time = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0

    # SLA compliance
    sla_compliant = len([t for t in all_tasks if t.get('status') == 'completed' and t.get('sla_met')])
    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)

    # Group by week
    by_week = {}
    for task in all_tasks:
        created_at = datetime.fromisoformat(task['created_at'])
        week_num = created_at.isocalendar()[1]
        if week_num not in by_week:
            by_week[week_num] = {'total': 0, 'completed': 0}
        by_week[week_num]['total'] += 1
        if task.get('status') == 'completed':
            by_week[week_num]['completed'] += 1

    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get('category', 'other')
        if category not in by_category:
            by_category[category] = {'count': 0, 'cost': 0}
        by_category[category]['count'] += 1
        by_category[category]['cost'] += task.get('cost', 0)

    # Most active rooms
    room_counts = {}
    for task in all_tasks:
        room = task.get('location', 'Unknown')
        room_counts[room] = room_counts.get(room, 0) + 1

    most_active_rooms = sorted(room_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Staff performance
    staff_performance = {}
    for task in all_tasks:
        if task.get('assigned_to'):
            staff = task['assigned_to']
            if staff not in staff_performance:
                staff_performance[staff] = {'tasks': 0, 'completed': 0, 'avg_time': 0}
            staff_performance[staff]['tasks'] += 1
            if task.get('status') == 'completed':
                staff_performance[staff]['completed'] += 1

    return {
        'period': {
            'month': month,
            'start': month_start.date().isoformat(),
            'end': month_end.date().isoformat()
        },
        'summary': {
            'total_tasks': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'cancelled': cancelled_tasks,
            'completion_rate': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1),
            'sla_compliance': sla_compliance_rate,
            'avg_response_time': avg_response_time,
            'avg_resolution_time': avg_resolution_time
        },
        'costs': {
            'total': round(total_cost, 2),
            'parts': round(parts_cost, 2),
            'labor': round(labor_cost, 2)
        },
        'by_week': by_week,
        'by_category': by_category,
        'most_active_rooms': [{'room': room, 'tasks': count} for room, count in most_active_rooms],
        'staff_performance': staff_performance
    }
# ── GET /maintenance/reports/summary ──
@router.get("/maintenance/reports/summary")
async def get_maintenance_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get quick maintenance summary for mobile dashboard"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)

    # Today's stats
    today_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$regex': f'^{today.date().isoformat()}'}
    })

    # Active tasks
    active_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['pending', 'in_progress']}
    })

    # Emergency tasks
    emergency_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': 'emergency',
        'status': {'$ne': 'completed'}
    })

    # This month's completion rate
    month_start = today.replace(day=1)
    month_tasks = []
    async for task in db.maintenance_tasks.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': month_start.isoformat()}
    }):
        month_tasks.append(task)

    completed_this_month = len([t for t in month_tasks if t.get('status') == 'completed'])
    completion_rate = round((completed_this_month / len(month_tasks) * 100) if month_tasks else 0, 1)

    return {
        'today_tasks': today_tasks,
        'active_tasks': active_tasks,
        'emergency_tasks': emergency_tasks,
        'completion_rate': completion_rate,
        'alerts': [
            {
                'type': 'emergency',
                'message': f'{emergency_tasks} acil görev bekliyor',
                'priority': 'high'
            } if emergency_tasks > 0 else None
        ]
    }
# ── GET /maintenance/calendar ──
@router.get("/maintenance/calendar")
async def get_maintenance_calendar(
    month: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get routine maintenance calendar"""
    current_user = await get_current_user(credentials)

    if not month:
        month = datetime.now(UTC).strftime('%Y-%m')

    # Get scheduled maintenance tasks
    year, m = month.split('-')
    next_month = int(m) + 1
    if next_month > 12:
        next_month = 1
        str(int(year) + 1)

    calendar_items = []

    # Mock routine maintenance schedule
    routine_tasks = [
        {'task': 'HVAC Filtre Değişimi', 'frequency': 'monthly', 'day': 5, 'duration': '2h'},
        {'task': 'Elektrik Panosu Kontrolü', 'frequency': 'monthly', 'day': 10, 'duration': '3h'},
        {'task': 'Yangın Alarm Testi', 'frequency': 'monthly', 'day': 15, 'duration': '1h'},
        {'task': 'Asansör Bakımı', 'frequency': 'monthly', 'day': 20, 'duration': '4h'},
        {'task': 'Su Tesisatı Kontrolü', 'frequency': 'monthly', 'day': 25, 'duration': '3h'}
    ]

    for task in routine_tasks:
        calendar_items.append({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'task_name': task['task'],
            'task_type': 'routine',
            'scheduled_date': f"{month}-{task['day']:02d}",
            'frequency': task['frequency'],
            'estimated_duration': task['duration'],
            'status': 'scheduled',
            'assigned_to': 'Maintenance Team'
        })

    return {
        'calendar': calendar_items,
        'month': month,
        'total_tasks': len(calendar_items)
    }
# ── POST /maintenance/schedule-routine ──
@router.post("/maintenance/schedule-routine")
async def schedule_routine_maintenance(
    schedule_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("maintenance")),  # v89 DW
):
    """Schedule a routine maintenance task"""
    current_user = await get_current_user(credentials)

    schedule = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_name': schedule_data.get('task_name'),
        'task_type': 'routine',
        'frequency': schedule_data.get('frequency'),  # daily, weekly, monthly, yearly
        'scheduled_date': schedule_data.get('scheduled_date'),
        'estimated_duration': schedule_data.get('estimated_duration'),
        'assigned_to': schedule_data.get('assigned_to'),
        'status': 'scheduled',
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.maintenance_schedule.insert_one(schedule)

    return {
        'message': 'Routine maintenance scheduled',
        'schedule_id': schedule['id']
    }
