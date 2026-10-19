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
from modules.pms_core.report_money import add_amount, rounded_totals, single_amount
from modules.pms_core.report_period import day_bounds, hotel_zone, instant_between, instant_value, local_today, parse_month
from modules.pms_core.role_permission_service import require_module_role  # v89 DW
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


def _measured(tasks: list[dict], field: str) -> list[float]:
    """Recorded values, zero included; missing or non-numeric left out."""
    values = []
    for task in tasks:
        value = task.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


async def _fallback_currency(tenant_id: str, tasks: list[dict]) -> str:
    """Currency of tasks stored without one: the hotel's currency."""
    if all(task.get("currency") for task in tasks):
        return "TRY"
    from core.tenant_currency import get_tenant_currency

    code, _symbol = await get_tenant_currency(tenant_id)
    return code


# ── GET /maintenance/reports/weekly ──
@router.get("/maintenance/reports/weekly")
async def get_weekly_maintenance_report(week_offset: int = 0, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get weekly maintenance report"""
    current_user = await get_current_user(credentials)

    # Monday 00:00 to Sunday 24:00 in the hotel's calendar (report_period).
    zone = await hotel_zone(db, current_user.tenant_id)
    today = local_today(zone, datetime.now(UTC))
    week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
    week_end = week_start + timedelta(days=6)
    lower, upper = day_bounds(week_start, week_end, zone)
    query = {"tenant_id": current_user.tenant_id, **instant_between("created_at", lower, upper)}

    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop("_id", None)
        all_tasks.append(task)

    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get("status") == "completed"])
    in_progress_tasks = len([t for t in all_tasks if t.get("status") == "in_progress"])
    pending_tasks = len([t for t in all_tasks if t.get("status") == "pending"])
    emergency_tasks = len([t for t in all_tasks if t.get("priority") == "emergency"])

    # Calculate SLA compliance
    sla_compliant = 0
    for task in all_tasks:
        if task.get("status") == "completed" and task.get("sla_met"):
            sla_compliant += 1

    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)
    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)

    # Calculate average response time (0 minutes is a real measurement)
    response_times = _measured(all_tasks, "response_time_minutes")
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0

    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get("category", "other")
        if category not in by_category:
            by_category[category] = {"count": 0, "completed": 0}
        by_category[category]["count"] += 1
        if task.get("status") == "completed":
            by_category[category]["completed"] += 1

    # Group by priority
    by_priority = {
        "emergency": len([t for t in all_tasks if t.get("priority") == "emergency"]),
        "high": len([t for t in all_tasks if t.get("priority") == "high"]),
        "normal": len([t for t in all_tasks if t.get("priority") == "normal"]),
        "low": len([t for t in all_tasks if t.get("priority") == "low"]),
    }

    # Top issues
    issue_counts = {}
    for task in all_tasks:
        issue = task.get("issue_type", "Other")
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "period": {"start": week_start.isoformat(), "end": week_end.isoformat(), "week_number": week_start.isocalendar()[1], "timezone": str(zone)},
        "summary": {
            "total_tasks": total_tasks,
            "completed": completed_tasks,
            "in_progress": in_progress_tasks,
            "pending": pending_tasks,
            "emergency": emergency_tasks,
            "completion_rate": completion_rate,
            "sla_compliance": sla_compliance_rate,
            "avg_response_time": avg_response_time,
        },
        "by_category": by_category,
        "by_priority": by_priority,
        "top_issues": [{"issue": issue, "count": count} for issue, count in top_issues],
        "tasks": all_tasks[:10],  # Latest 10 tasks
    }


# ── GET /maintenance/reports/monthly ──
@router.get("/maintenance/reports/monthly")
async def get_monthly_maintenance_report(month: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get monthly maintenance report"""
    current_user = await get_current_user(credentials)

    zone = await hotel_zone(db, current_user.tenant_id)
    if not month:
        month = local_today(zone, datetime.now(UTC)).strftime("%Y-%m")
    # Whole calendar month in the hotel's time zone, last day included.
    month_start, month_end = parse_month(month)
    lower, upper = day_bounds(month_start, month_end, zone)
    query = {"tenant_id": current_user.tenant_id, **instant_between("created_at", lower, upper)}

    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop("_id", None)
        all_tasks.append(task)

    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get("status") == "completed"])
    in_progress_tasks = len([t for t in all_tasks if t.get("status") == "in_progress"])
    pending_tasks = len([t for t in all_tasks if t.get("status") == "pending"])
    cancelled_tasks = len([t for t in all_tasks if t.get("status") == "cancelled"])

    # Costs per currency; never added across currencies, never converted.
    fallback = await _fallback_currency(current_user.tenant_id, all_tasks)
    totals: dict[str, dict] = {"cost": {}, "parts_cost": {}, "labor_cost": {}}
    for task in all_tasks:
        code = task.get("currency") or fallback
        for field, bucket in totals.items():
            if task.get(field):
                add_amount(bucket, code, task[field])

    # Calculate times (0 minutes is a real measurement)
    response_times = _measured(all_tasks, "response_time_minutes")
    resolution_times = _measured(all_tasks, "resolution_time_minutes")

    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0
    avg_resolution_time = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0

    # SLA compliance
    sla_compliant = len([t for t in all_tasks if t.get("status") == "completed" and t.get("sla_met")])
    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)

    # Group by week
    by_week = {}
    for task in all_tasks:
        created_at = instant_value(task.get("created_at"))
        if created_at is None:
            continue
        week_num = created_at.astimezone(zone).isocalendar()[1]
        if week_num not in by_week:
            by_week[week_num] = {"total": 0, "completed": 0}
        by_week[week_num]["total"] += 1
        if task.get("status") == "completed":
            by_week[week_num]["completed"] += 1

    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get("category", "other")
        if category not in by_category:
            by_category[category] = {"count": 0, "cost_by_currency": {}}
        by_category[category]["count"] += 1
        if task.get("cost"):
            add_amount(by_category[category]["cost_by_currency"], task.get("currency") or fallback, task["cost"])
    for row in by_category.values():
        row["cost_by_currency"] = rounded_totals(row["cost_by_currency"])
        row["cost"] = single_amount(row["cost_by_currency"])

    # Most active rooms
    room_counts = {}
    for task in all_tasks:
        room = task.get("location", "Unknown")
        room_counts[room] = room_counts.get(room, 0) + 1

    most_active_rooms = sorted(room_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Staff performance
    staff_performance = {}
    for task in all_tasks:
        if task.get("assigned_to"):
            staff = task["assigned_to"]
            if staff not in staff_performance:
                staff_performance[staff] = {"tasks": 0, "completed": 0, "avg_time": 0}
            staff_performance[staff]["tasks"] += 1
            if task.get("status") == "completed":
                staff_performance[staff]["completed"] += 1

    return {
        "period": {"month": month, "start": month_start.isoformat(), "end": month_end.isoformat(), "timezone": str(zone)},
        "summary": {
            "total_tasks": total_tasks,
            "completed": completed_tasks,
            "in_progress": in_progress_tasks,
            "pending": pending_tasks,
            "cancelled": cancelled_tasks,
            "completion_rate": round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1),
            "sla_compliance": sla_compliance_rate,
            "avg_response_time": avg_response_time,
            "avg_resolution_time": avg_resolution_time,
        },
        # One currency: the scalar is that amount; several: null, use *_by_currency.
        "costs": {
            "total": single_amount(totals["cost"]), "parts": single_amount(totals["parts_cost"]), "labor": single_amount(totals["labor_cost"]),
            "total_by_currency": rounded_totals(totals["cost"]), "parts_by_currency": rounded_totals(totals["parts_cost"]),
            "labor_by_currency": rounded_totals(totals["labor_cost"]),
        },
        "by_week": by_week,
        "by_category": by_category,
        "most_active_rooms": [{"room": room, "tasks": count} for room, count in most_active_rooms],
        "staff_performance": staff_performance,
    }


# ── GET /maintenance/reports/summary ──
@router.get("/maintenance/reports/summary")
async def get_maintenance_summary(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get quick maintenance summary for mobile dashboard"""
    current_user = await get_current_user(credentials)

    # "Today" and "this month" are the hotel's local calendar, for ISO-text
    # and BSON created_at alike (a UTC-prefix match missed 00:00-03:00 local).
    zone = await hotel_zone(db, current_user.tenant_id)
    today = local_today(zone, datetime.now(UTC))
    today_tasks = await db.maintenance_tasks.count_documents(
        {"tenant_id": current_user.tenant_id, **instant_between("created_at", *day_bounds(today, today, zone))})

    # Active tasks
    active_tasks = await db.maintenance_tasks.count_documents({"tenant_id": current_user.tenant_id, "status": {"$in": ["pending", "in_progress"]}})

    # Emergency tasks
    emergency_tasks = await db.maintenance_tasks.count_documents({"tenant_id": current_user.tenant_id, "priority": "emergency", "status": {"$ne": "completed"}})

    # This month's completion rate
    month_tasks = await db.maintenance_tasks.find(
        {"tenant_id": current_user.tenant_id, **instant_between("created_at", *day_bounds(today.replace(day=1), today, zone))},
        {"_id": 0, "status": 1},
    ).to_list(None)

    completed_this_month = len([t for t in month_tasks if t.get("status") == "completed"])
    completion_rate = round((completed_this_month / len(month_tasks) * 100) if month_tasks else 0, 1)

    return {
        "today_tasks": today_tasks,
        "active_tasks": active_tasks,
        "emergency_tasks": emergency_tasks,
        "completion_rate": completion_rate,
        "alerts": [{"type": "emergency", "message": f"{emergency_tasks} acil görev bekliyor", "priority": "high"} if emergency_tasks > 0 else None],
    }


# ── GET /maintenance/calendar ──
@router.get("/maintenance/calendar")
async def get_maintenance_calendar(month: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get routine maintenance calendar"""
    current_user = await get_current_user(credentials)

    if month:
        parse_month(month)  # malformed -> 422
    else:
        month = local_today(await hotel_zone(db, current_user.tenant_id), datetime.now(UTC)).strftime("%Y-%m")

    # Gercek planli bakim kayitlari `maintenance_schedule` koleksiyonunda tutulur
    # (POST /maintenance/schedule-routine ile yazilir). Uydurma sabit takvim
    # uretmek yerine tenant'a ait gercek kayitlari ay bazinda sorgula.
    calendar_items = (
        await db.maintenance_schedule.find(
            {
                "tenant_id": current_user.tenant_id,
                "scheduled_date": {"$regex": f"^{month}"},
            },
            {"_id": 0},
        )
        .sort("scheduled_date", 1)
        .to_list(length=None)
    )

    return {
        "calendar": calendar_items,
        "month": month,
        "total_tasks": len(calendar_items),
        "data_available": bool(calendar_items),
    }


# ── POST /maintenance/schedule-routine ──
@router.post("/maintenance/schedule-routine")
async def schedule_routine_maintenance(
    schedule_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_role("maintenance")),  # v89 DW
):
    """Schedule a routine maintenance task"""
    current_user = await get_current_user(credentials)

    schedule = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "task_name": schedule_data.get("task_name"),
        "task_type": "routine",
        "frequency": schedule_data.get("frequency"),  # daily, weekly, monthly, yearly
        "scheduled_date": schedule_data.get("scheduled_date"),
        "estimated_duration": schedule_data.get("estimated_duration"),
        "assigned_to": schedule_data.get("assigned_to"),
        "status": "scheduled",
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db.maintenance_schedule.insert_one(schedule)

    return {"message": "Routine maintenance scheduled", "schedule_id": schedule["id"]}
