from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.security import _is_super_admin, get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contact-center", tags=["contact-center-reports"])


def _require_supervisor(current_user: User):
    """Enforce that only supervisor, admin, or super_admin can perform action."""
    if _is_super_admin(current_user):
        return
    role_val = getattr(current_user.role, "value", str(current_user.role))
    if role_val not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")


def _safe_seconds_between(dt1, dt2) -> float:
    if not dt1 or not dt2:
        return 0.0
    if isinstance(dt1, str):
        dt1 = datetime.fromisoformat(dt1.replace("Z", "+00:00"))
    if isinstance(dt2, str):
        dt2 = datetime.fromisoformat(dt2.replace("Z", "+00:00"))
    return abs((dt1 - dt2).total_seconds())


@router.get("/reports")
async def get_performance_reports(
    start_date: str | None = None,
    end_date: str | None = None,
    queue_id: str | None = None,
    agent_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Omnichannel Performance Report containing SLA, ASA, AHT, FCR, and Conversion metrics."""
    _require_supervisor(current_user)
    tenant_id = current_user.tenant_id

    # 1. Build calls query
    call_query: dict = {"tenant_id": tenant_id}
    if queue_id:
        call_query["queue_id"] = queue_id
    if agent_id:
        call_query["agent_id"] = agent_id

    date_filter = {}
    if start_date:
        try:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        except ValueError:
            pass
    if date_filter:
        call_query["started_at"] = date_filter

    # Fetch all calls matching criteria
    calls_cursor = db.contact_center_calls.find(call_query)
    calls = await calls_cursor.to_list(length=5000)

    # Fetch all dispositions for this tenant to cross-reference (ACW, FCR, Reservation link)
    disp_cursor = db.contact_center_dispositions.find({"tenant_id": tenant_id})
    dispositions = await disp_cursor.to_list(length=5000)
    disp_map = {d["call_id"]: d for d in dispositions if d.get("call_id")}

    # Fetch queue configs to get SLA thresholds
    queue_cursor = db.contact_center_queues.find({"tenant_id": tenant_id})
    queues = await queue_cursor.to_list(length=100)
    queue_map = {q["id"]: q for q in queues}

    # Fetch users/agents roster to map names
    agents_cursor = db.users.find({"tenant_id": tenant_id})
    agents_map = {u["id"]: u.get("name") or u.get("username") async for u in agents_cursor}

    # Metrics calculation
    total_calls = len(calls)
    answered_calls = [c for c in calls if c.get("answered_at")]
    abandoned_calls = [c for c in calls if c.get("status") in ["missed", "failed"] and not c.get("answered_at")]

    # SLA Calculations
    met_sla_count = 0
    total_wait_time = 0.0
    total_handle_time = 0.0
    total_acw_time = 0.0
    resolved_fcr_count = 0
    converted_reservations_count = 0

    for c in answered_calls:
        c_id = c["id"]
        started = c.get("started_at")
        answered = c.get("answered_at")
        ended = c.get("ended_at")

        # 1. Wait Time (Speed of Answer)
        wait_sec = _safe_seconds_between(answered, started)
        total_wait_time += wait_sec

        # 2. SLA threshold
        q_id = c.get("queue_id")
        threshold = 20
        if q_id and q_id in queue_map:
            threshold = queue_map[q_id].get("sla_threshold_seconds") or 20
        if wait_sec <= threshold:
            met_sla_count += 1

        # 3. Talk Time (duration)
        talk_sec = float(c.get("duration_seconds") or 0.0)
        if talk_sec == 0.0 and ended and answered:
            talk_sec = _safe_seconds_between(ended, answered)

        # 4. ACW Time
        acw_sec = 0.0
        disp = disp_map.get(c_id)
        if disp:
            acw_sec = _safe_seconds_between(disp.get("created_at"), ended)
            # FCR
            tags = disp.get("tags") or []
            if "fcr" in tags or "resolved" in tags:
                resolved_fcr_count += 1
            # Reservation conversion
            if disp.get("linked_reservation_id") or disp.get("linked_complaint_id"):
                converted_reservations_count += 1
        elif c.get("linked_reservation_id"):
            converted_reservations_count += 1

        total_acw_time += acw_sec
        total_handle_time += talk_sec + acw_sec

    answered_count = len(answered_calls)
    abandoned_count = len(abandoned_calls)

    sla_pct = (met_sla_count / answered_count * 100.0) if answered_count > 0 else 100.0
    asa = (total_wait_time / answered_count) if answered_count > 0 else 0.0
    aht = (total_handle_time / answered_count) if answered_count > 0 else 0.0
    avg_acw = (total_acw_time / answered_count) if answered_count > 0 else 0.0
    fcr_rate = (resolved_fcr_count / answered_count * 100.0) if answered_count > 0 else 0.0
    conversion_rate = (converted_reservations_count / total_calls * 100.0) if total_calls > 0 else 0.0

    # Callbacks metrics
    cb_query = {"tenant_id": tenant_id}
    if start_date:
        try:
            cb_query["abandoned_at"] = {"$gte": datetime.fromisoformat(start_date)}
        except ValueError:
            pass
    callbacks_cursor = db.contact_center_callbacks.find(cb_query)
    callbacks = await callbacks_cursor.to_list(length=1000)
    total_callbacks = len(callbacks)
    completed_callbacks = sum(1 for cb in callbacks if cb.get("status") == "completed")
    callback_success_rate = (completed_callbacks / total_callbacks * 100.0) if total_callbacks > 0 else 100.0

    # Agent breakdown
    agent_stats: dict = {}
    for c in answered_calls:
        a_id = c.get("agent_id")
        if not a_id:
            continue
        if a_id not in agent_stats:
            agent_stats[a_id] = {
                "agent_id": a_id,
                "agent_name": agents_map.get(a_id) or f"Agent {a_id}",
                "answered_count": 0,
                "total_wait_time": 0.0,
                "total_handle_time": 0.0,
                "resolved_fcr_count": 0,
                "converted_reservations_count": 0,
            }

        stat = agent_stats[a_id]
        stat["answered_count"] += 1

        # Wait
        wait_sec = _safe_seconds_between(c.get("answered_at"), c.get("started_at"))
        stat["total_wait_time"] += wait_sec

        # Talk + ACW
        talk_sec = float(c.get("duration_seconds") or 0.0)
        acw_sec = 0.0
        disp = disp_map.get(c["id"])
        if disp:
            acw_sec = _safe_seconds_between(disp.get("created_at"), c.get("ended_at"))
            tags = disp.get("tags") or []
            if "fcr" in tags or "resolved" in tags:
                stat["resolved_fcr_count"] += 1
            if disp.get("linked_reservation_id"):
                stat["converted_reservations_count"] += 1

        stat["total_handle_time"] += talk_sec + acw_sec

    agent_breakdown_list = []
    for stat in agent_stats.values():
        acnt = stat["answered_count"]
        agent_breakdown_list.append(
            {
                "agent_id": stat["agent_id"],
                "agent_name": stat["agent_name"],
                "answered_count": acnt,
                "asa_seconds": round(stat["total_wait_time"] / acnt, 2) if acnt > 0 else 0.0,
                "aht_seconds": round(stat["total_handle_time"] / acnt, 2) if acnt > 0 else 0.0,
                "fcr_percentage": round(stat["resolved_fcr_count"] / acnt * 100.0, 2) if acnt > 0 else 0.0,
                "conversion_count": stat["converted_reservations_count"],
            }
        )

    # Queue breakdown
    queue_stats: dict = {}
    for c in calls:
        q_id = c.get("queue_id") or "unassigned"
        q_name = queue_map[q_id].get("name") if q_id in queue_map else "No Queue / Direct Extension"
        if q_id not in queue_stats:
            queue_stats[q_id] = {"queue_id": q_id, "queue_name": q_name, "total_calls": 0, "answered_count": 0, "abandoned_count": 0, "met_sla_count": 0, "total_wait_time": 0.0}

        stat = queue_stats[q_id]
        stat["total_calls"] += 1

        if c.get("answered_at"):
            stat["answered_count"] += 1
            wait_sec = _safe_seconds_between(c.get("answered_at"), c.get("started_at"))
            stat["total_wait_time"] += wait_sec

            threshold = 20
            if q_id in queue_map:
                threshold = queue_map[q_id].get("sla_threshold_seconds") or 20
            if wait_sec <= threshold:
                stat["met_sla_count"] += 1
        elif c.get("status") in ["missed", "failed"]:
            stat["abandoned_count"] += 1

    queue_breakdown_list = []
    for stat in queue_stats.values():
        total_q = stat["total_calls"]
        acnt = stat["answered_count"]
        queue_breakdown_list.append(
            {
                "queue_id": stat["queue_id"],
                "queue_name": stat["queue_name"],
                "total_calls": total_q,
                "answered_count": acnt,
                "abandoned_count": stat["abandoned_count"],
                "sla_percentage": round(stat["met_sla_count"] / acnt * 100.0, 2) if acnt > 0 else 100.0,
                "asa_seconds": round(stat["total_wait_time"] / acnt, 2) if acnt > 0 else 0.0,
            }
        )

    return {
        "summary": {
            "total_calls": total_calls,
            "answered_count": answered_count,
            "abandoned_count": abandoned_count,
            "sla_percentage": round(sla_pct, 2),
            "asa_seconds": round(asa, 2),
            "aht_seconds": round(aht, 2),
            "average_acw_seconds": round(avg_acw, 2),
            "fcr_percentage": round(fcr_rate, 2),
            "callback_success_rate": round(callback_success_rate, 2),
            "reservation_conversion_rate": round(conversion_rate, 2),
        },
        "agent_breakdown": agent_breakdown_list,
        "queue_breakdown": queue_breakdown_list,
    }
