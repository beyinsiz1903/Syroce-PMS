"""
housekeeping

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW

logger = logging.getLogger(__name__)
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from core.database import db
from core.security import get_current_user
from core.utils import create_excel_workbook, excel_response
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


# ── POST /housekeeping/start-cleaning/{room_id} ──
@router.post("/housekeeping/start-cleaning/{room_id}")
async def start_cleaning_timer(
    room_id: str,
    staff_info: dict = {},
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Start cleaning timer for a room"""
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Create cleaning task
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'assigned_to': staff_info.get('staff_name', current_user.name),
        'assigned_id': staff_info.get('staff_id', current_user.id),
        'started_at': datetime.now(UTC).isoformat(),
        'completed_at': None,
        'status': 'in_progress',
        'duration_minutes': None,
        'notes': staff_info.get('notes', '')
    }

    await db.housekeeping_tasks.insert_one(task)

    # Update room status — v109 round-9 IDOR: scope by tenant.
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'cleaning',
                'assigned_cleaner': task['assigned_to'],
                'cleaning_started_at': task['started_at'],
                'current_task_id': task_id
            }
        }
    )

    # v95.2 — yeni timer başlayınca aktif timer + performance cache invalidasyon
    try:
        if cache:
            cache.invalidate_tenant_cache(current_user.tenant_id, "hk_active_timers")
            cache.invalidate_tenant_cache(current_user.tenant_id, "housekeeping_performance")
            cache.invalidate_tenant_cache(current_user.tenant_id, "housekeeping_room_status")
    except Exception:
        pass

    return {
        'success': True,
        'task_id': task_id,
        'room_number': room.get('room_number'),
        'started_at': task['started_at'],
        'assigned_to': task['assigned_to']
    }
# ── POST /housekeeping/complete-cleaning/{task_id} ──
@router.post("/housekeeping/complete-cleaning/{task_id}")
async def complete_cleaning_timer(
    task_id: str,
    completion_data: dict = {},
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Complete cleaning timer and update room status"""
    task = await db.housekeeping_tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Calculate duration
    started_at = datetime.fromisoformat(task['started_at'])
    completed_at = datetime.now(UTC)
    duration = (completed_at - started_at).total_seconds() / 60  # minutes

    # v95.2 IDOR — tenant_id filter'ı eksikti; başka tenant'ın task_id'si
    # tahmin edilirse (UUID4 zorlu ama prensibe aykırı) cross-tenant update
    # yapabiliyordu. Atomik olarak tenant'a sabitle.
    await db.housekeeping_tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'completed_at': completed_at.isoformat(),
                'status': 'completed',
                'duration_minutes': round(duration, 1),
                'completion_notes': completion_data.get('notes', ''),
                'quality_score': completion_data.get('quality_score', 5)
            }
        }
    )

    # Update room status — v109 round-9 IDOR: scope by tenant.
    await db.rooms.update_one(
        {'id': task['room_id'], 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'inspected',
                'cleaning_completed_at': completed_at.isoformat(),
                'last_cleaned': completed_at.isoformat(),
                'current_task_id': None
            }
        }
    )

    # v95.2 — timer kapandıktan sonra cache invalidasyon
    try:
        if cache:
            cache.invalidate_tenant_cache(current_user.tenant_id, "hk_active_timers")
            cache.invalidate_tenant_cache(current_user.tenant_id, "housekeeping_performance")
            cache.invalidate_tenant_cache(current_user.tenant_id, "housekeeping_room_status")
    except Exception:
        pass

    return {
        'success': True,
        'task_id': task_id,
        'room_number': task['room_number'],
        'duration_minutes': round(duration, 1),
        'completed_at': completed_at.isoformat()
    }
# ── GET /housekeeping/active-timers ──
@router.get("/housekeeping/active-timers")
@cached(ttl=60, key_prefix="hk_active_timers")  # Cache for 1 min
async def get_active_cleaning_timers(current_user: User = Depends(get_current_user)):
    """Get all active cleaning timers"""
    tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'in_progress'
    }).to_list(100)

    # v95 — Resolve room_id → room_number via single batch lookup
    room_ids = {t.get('room_id') for t in tasks if t.get('room_id') and not t.get('room_number')}
    room_map: dict[str, str] = {}
    if room_ids:
        async for r in db.rooms.find(
            {'tenant_id': current_user.tenant_id, 'id': {'$in': list(room_ids)}},
            {'_id': 0, 'id': 1, 'room_number': 1}
        ):
            room_map[r['id']] = r.get('room_number', '?')

    now = datetime.now(UTC)
    active_timers = []

    for task in tasks:
        # Defensive: legacy tasks may miss started_at / room_number / assigned_to
        started_raw = task.get('started_at')
        if not started_raw:
            continue
        try:
            started_at = datetime.fromisoformat(started_raw)
        except (ValueError, TypeError):
            continue
        elapsed = (now - started_at).total_seconds() / 60  # minutes

        # Prefer denormalized room_number, fall back to lookup-resolved name
        room_number = (
            task.get('room_number')
            or room_map.get(task.get('room_id'), '?')
        )

        active_timers.append({
            'task_id': task.get('id'),
            'room_number': room_number,
            'assigned_to': task.get('assigned_to'),
            'started_at': started_raw,
            'elapsed_minutes': round(elapsed, 1),
            'status': 'in_progress'
        })

    return {
        'active_timers': active_timers,
        'total_active': len(active_timers)
    }
# ── GET /housekeeping/performance-stats ──
@router.get("/housekeeping/performance-stats")
@cached(ttl=600, key_prefix="housekeeping_performance")  # Cache for 10 minutes
async def get_housekeeping_performance_stats(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v84 DT: HK perf (yönetim)
):
    """Get housekeeping performance statistics"""
    since = datetime.now(UTC) - timedelta(days=days)

    completed_tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': since.isoformat()}
    }).to_list(10000)

    if not completed_tasks:
        return {
            'average_duration': 0,
            'total_rooms_cleaned': 0,
            'fastest_cleaning': 0,
            'slowest_cleaning': 0,
            'staff_performance': []
        }

    durations = [t['duration_minutes'] for t in completed_tasks if t.get('duration_minutes')]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Staff performance
    staff_stats = {}
    for task in completed_tasks:
        staff = task.get('assigned_to', 'Unknown')
        if staff not in staff_stats:
            staff_stats[staff] = {
                'name': staff,
                'rooms_cleaned': 0,
                'total_duration': 0,
                'avg_duration': 0
            }
        staff_stats[staff]['rooms_cleaned'] += 1
        staff_stats[staff]['total_duration'] += task.get('duration_minutes', 0)

    for staff in staff_stats.values():
        staff['avg_duration'] = round(staff['total_duration'] / staff['rooms_cleaned'], 1) if staff['rooms_cleaned'] > 0 else 0

    return {
        'period_days': days,
        'average_duration': round(avg_duration, 1),
        'total_rooms_cleaned': len(completed_tasks),
        'fastest_cleaning': round(min(durations), 1) if durations else 0,
        'slowest_cleaning': round(max(durations), 1) if durations else 0,
        'staff_performance': sorted(staff_stats.values(), key=lambda x: x['rooms_cleaned'], reverse=True)
    }
# ── GET /housekeeping/staff/{staff_id}/detailed-stats ──
@router.get("/housekeeping/staff/{staff_id}/detailed-stats")
@cached(ttl=600, key_prefix="staff_detailed_stats")  # Cache for 10 min
async def get_staff_detailed_statistics(
    staff_id: str,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v84 DT: staff perf (yönetim)
):
    """Detailed staff performance by room type, shift, and speed"""
    since = datetime.now(UTC) - timedelta(days=days)

    # Get all tasks for this staff member
    tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'assigned_id': staff_id,
        'status': 'completed',
        'completed_at': {'$gte': since.isoformat()}
    }).to_list(10000)

    if not tasks:
        return {'error': 'No data for this staff member'}

    # Get staff info
    staff = await db.users.find_one({'id': staff_id}) or await db.staff.find_one({'id': staff_id})

    # BY ROOM TYPE
    by_room_type = {}
    for task in tasks:
        room = await db.rooms.find_one({'id': task['room_id']})
        room_type = room.get('room_type', 'unknown') if room else 'unknown'

        if room_type not in by_room_type:
            by_room_type[room_type] = {
                'count': 0,
                'total_duration': 0,
                'avg_duration': 0,
                'fastest': 999,
                'slowest': 0
            }

        duration = task.get('duration_minutes', 0)
        by_room_type[room_type]['count'] += 1
        by_room_type[room_type]['total_duration'] += duration
        by_room_type[room_type]['fastest'] = min(by_room_type[room_type]['fastest'], duration)
        by_room_type[room_type]['slowest'] = max(by_room_type[room_type]['slowest'], duration)

    for stats in by_room_type.values():
        stats['avg_duration'] = round(stats['total_duration'] / stats['count'], 1) if stats['count'] > 0 else 0

    # BY SHIFT (Morning / Afternoon / Night)
    by_shift = {'morning': [], 'afternoon': [], 'evening': []}
    for task in tasks:
        started_at = datetime.fromisoformat(task['started_at'])
        hour = started_at.hour

        if 6 <= hour < 14:
            by_shift['morning'].append(task)
        elif 14 <= hour < 22:
            by_shift['afternoon'].append(task)
        else:
            by_shift['evening'].append(task)

    shift_stats = {}
    for shift, shift_tasks in by_shift.items():
        if shift_tasks:
            durations = [t.get('duration_minutes', 0) for t in shift_tasks]
            shift_stats[shift] = {
                'rooms_cleaned': len(shift_tasks),
                'avg_duration': round(sum(durations) / len(durations), 1),
                'total_hours': round(sum(durations) / 60, 1)
            }
        else:
            shift_stats[shift] = {'rooms_cleaned': 0, 'avg_duration': 0, 'total_hours': 0}

    # SPEED ANALYSIS
    all_durations = [t.get('duration_minutes', 0) for t in tasks]
    avg_duration = sum(all_durations) / len(all_durations)

    # Compare to hotel average
    hotel_tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': since.isoformat()}
    }).to_list(100000)

    hotel_durations = [t.get('duration_minutes', 0) for t in hotel_tasks]
    hotel_avg = sum(hotel_durations) / len(hotel_durations) if hotel_durations else 0

    speed_rating = 'average'
    if avg_duration < hotel_avg * 0.85:
        speed_rating = 'fast'
    elif avg_duration > hotel_avg * 1.15:
        speed_rating = 'slow'

    # QUALITY SCORES
    quality_scores = [t.get('quality_score', 5) for t in tasks if t.get('quality_score')]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 5

    # DAY-by-DAY PERFORMANCE
    daily_performance = {}
    for task in tasks:
        date = task['started_at'][:10]
        if date not in daily_performance:
            daily_performance[date] = {'rooms': 0, 'total_time': 0}
        daily_performance[date]['rooms'] += 1
        daily_performance[date]['total_time'] += task.get('duration_minutes', 0)

    return {
        'staff_info': {
            'id': staff_id,
            'name': staff.get('name', 'Unknown') if staff else 'Unknown',
            'email': staff.get('email', '') if staff else ''
        },
        'period': {
            'days': days,
            'start_date': since.isoformat(),
            'end_date': datetime.now(UTC).isoformat()
        },
        'overall': {
            'total_rooms_cleaned': len(tasks),
            'avg_duration': round(avg_duration, 1),
            'fastest_cleaning': round(min(all_durations), 1),
            'slowest_cleaning': round(max(all_durations), 1),
            'avg_quality_score': round(avg_quality, 1),
            'speed_rating': speed_rating,
            'vs_hotel_avg': round(((avg_duration - hotel_avg) / hotel_avg * 100) if hotel_avg > 0 else 0, 1)
        },
        'by_room_type': by_room_type,
        'by_shift': shift_stats,
        'daily_performance': daily_performance
    }
# ── GET /reports/housekeeping-efficiency ──
@router.get("/reports/housekeeping-efficiency")
@cached(ttl=600, key_prefix="report_hk_efficiency")  # Cache for 10 min
async def get_housekeeping_efficiency_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v85 DU: HK efficiency rapor
):
    """Housekeeping Efficiency Report"""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    # Get completed housekeeping tasks in date range
    tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'created_at': {'$gte': start.isoformat(), '$lte': end.isoformat()}
    }).to_list(10000)

    # Aggregate by assigned staff
    staff_performance = {}

    for task in tasks:
        assigned_to = task.get('assigned_to', 'Unassigned')
        task_type = task.get('task_type', 'cleaning')

        if assigned_to not in staff_performance:
            staff_performance[assigned_to] = {
                'tasks_completed': 0,
                'by_type': {}
            }

        staff_performance[assigned_to]['tasks_completed'] += 1

        if task_type not in staff_performance[assigned_to]['by_type']:
            staff_performance[assigned_to]['by_type'][task_type] = 0
        staff_performance[assigned_to]['by_type'][task_type] += 1

    # Calculate daily averages
    date_range_days = (end.date() - start.date()).days + 1

    for staff in staff_performance:
        staff_performance[staff]['daily_average'] = round(
            staff_performance[staff]['tasks_completed'] / date_range_days, 2
        )

    return {
        'start_date': start_date,
        'end_date': end_date,
        'date_range_days': date_range_days,
        'total_tasks_completed': len(tasks),
        'staff_performance': staff_performance,
        'daily_average_all_staff': round(len(tasks) / date_range_days, 2) if date_range_days > 0 else 0
    }
# ── GET /reports/housekeeping-efficiency/excel ──
@router.get("/reports/housekeeping-efficiency/excel")
@cached(ttl=900, key_prefix="report_hk_efficiency_excel")  # Cache for 15 min
async def export_housekeeping_efficiency_excel(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v85 DU: HK efficiency excel
):
    """Export Housekeeping Efficiency Report to Excel"""
    report_data = await get_housekeeping_efficiency_report(start_date, end_date, current_user)

    headers = ["Staff Member", "Tasks Completed", "Daily Average", "Cleaning", "Maintenance", "Inspection"]
    data = []

    for staff, performance in report_data['staff_performance'].items():
        by_type = performance['by_type']
        data.append([
            staff,
            performance['tasks_completed'],
            f"{performance['daily_average']:.2f}",
            by_type.get('cleaning', 0),
            by_type.get('maintenance', 0),
            by_type.get('inspection', 0)
        ])

    wb = create_excel_workbook(
        title=f"Housekeeping Efficiency Report ({start_date} to {end_date})",
        headers=headers,
        data=data,
        sheet_name="HK Efficiency"
    )

    filename = f"housekeeping_efficiency_{start_date}_to_{end_date}.xlsx"
    return excel_response(wb, filename)
