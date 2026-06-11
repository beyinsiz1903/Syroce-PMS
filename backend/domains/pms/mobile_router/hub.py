"""
hub

Task #327 — Faz 0 Mobil Ortak Omurga (Tier 1 backbone).

Person-centric aggregation endpoints for the unified mobile shell. These
endpoints DO NOT introduce any new data, notification types, or triggers —
they merge data that already exists in the system (notifications, alerts,
housekeeping/maintenance tasks, finance + HR approvals) into the single
common views the mobile shell renders.

All endpoints are tenant-scoped via the authenticated user and reuse the
existing collections + read-state semantics. Approval visibility is gated
with the SAME RolePermissionService used elsewhere, so nothing weakens RBAC.
"""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import _is_super_admin, get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService

router = APIRouter(prefix="/api/mobile/hub", tags=["mobile / hub"])

_DONE_TASK_STATUSES = {"completed", "done", "cancelled", "verified", "closed"}


def _assignee_names(user: User) -> list[str]:
    """Names a task/alert may be assigned to for this user.

    Housekeeping tasks, maintenance tasks and alerts store `assigned_to`
    as a free-text staff NAME string (not a user id), so we match against
    both the display name and the login username.
    """
    names: list[str] = []
    for candidate in (getattr(user, "name", None), getattr(user, "username", None)):
        if candidate and candidate not in names:
            names.append(candidate)
    return names


def _sort_key(value: Any) -> str:
    """Stable descending-sort key for ISO timestamps that may be missing."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return ""


def _can(user: User, operation: str) -> bool:
    """Imperative permission probe mirroring require_op (super-admin bypass)."""
    if _is_super_admin(user):
        return True
    return RolePermissionService().check_permission(
        user.role,
        operation,
        granted_permissions=getattr(user, "granted_permissions", None),
    )


# ── 1. Unified notification feed ────────────────────────────────────────────


@router.get("/feed")
async def get_unified_feed(
    limit: int = 30,
    offset: int = 0,
    unread_only: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Merge `notifications` + `alerts` into one paginated, read-stateful feed.

    - notifications: addressed to this user OR system-wide (user_id None).
    - alerts: assigned to this user's name OR general (assigned_to None).
    Each item carries `source` so the mark-read endpoint can route correctly.
    """
    current_user = await get_current_user(credentials)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    fetch_cap = offset + limit

    names = _assignee_names(current_user)

    notif_query: dict[str, Any] = {
        "$or": [
            {"user_id": current_user.id},
            {"tenant_id": current_user.tenant_id, "user_id": None},
        ]
    }
    if unread_only:
        notif_query["read"] = False

    alert_match: dict[str, Any] = {
        "tenant_id": current_user.tenant_id,
        "$or": [
            {"assigned_to": {"$in": names}} if names else {"assigned_to": "__none__"},
            {"assigned_to": None},
        ],
    }
    if unread_only:
        alert_match["status"] = "unread"

    items: list[dict[str, Any]] = []

    async for n in (
        db.notifications.find(notif_query).sort("created_at", -1).limit(fetch_cap)
    ):
        items.append(
            {
                "source": "notification",
                "id": n.get("id"),
                "type": n.get("type", "general"),
                "title": n.get("title", ""),
                "message": n.get("message", "") or n.get("body", ""),
                "priority": n.get("priority", "normal"),
                "read": bool(n.get("read", False)),
                "action_url": n.get("action_url"),
                "created_at": _sort_key(n.get("created_at")),
            }
        )

    async for a in db.alerts.find(alert_match).sort("created_at", -1).limit(fetch_cap):
        status = a.get("status", "unread")
        items.append(
            {
                "source": "alert",
                "id": a.get("id"),
                "type": a.get("alert_type", "alert"),
                "title": a.get("title", ""),
                "message": a.get("description", ""),
                "priority": a.get("priority", "normal"),
                "read": status not in (None, "unread"),
                "action_url": a.get("action_url"),
                "created_at": _sort_key(a.get("created_at")),
            }
        )

    items.sort(key=lambda x: x["created_at"], reverse=True)
    page = items[offset : offset + limit]

    unread_notifs = await db.notifications.count_documents({**notif_query, "read": False})
    unread_alerts = await db.alerts.count_documents({**alert_match, "status": "unread"})

    return {
        "items": page,
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "has_more": len(items) > offset + limit,
        "unread_count": unread_notifs + unread_alerts,
    }


class FeedMarkReadRequest(BaseModel):
    source: str  # "notification" | "alert"
    id: str


@router.post("/feed/mark-read")
async def mark_feed_item_read(
    request: FeedMarkReadRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Mark a single feed item read in its origin collection.

    Routes by `source` and reuses the exact read-state shape the legacy
    notification/inbox endpoints write, so the UI stays consistent.
    """
    current_user = await get_current_user(credentials)
    now = datetime.now(UTC).isoformat()

    if request.source == "notification":
        result = await db.notifications.update_one(
            {
                "id": request.id,
                "$or": [
                    {"user_id": current_user.id},
                    {"tenant_id": current_user.tenant_id},
                ],
            },
            {"$set": {"read": True, "read_at": now}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Bildirim bulunamadı")
    elif request.source == "alert":
        result = await db.alerts.update_one(
            {"id": request.id, "tenant_id": current_user.tenant_id},
            {"$set": {"status": "read", "read_at": now}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Uyarı bulunamadı")
    else:
        raise HTTPException(status_code=400, detail="Geçersiz kaynak")

    return {"success": True, "source": request.source, "id": request.id}


# ── 2. "Görevlerim" — my tasks (housekeeping + maintenance) ─────────────────


async def _collect_my_tasks(current_user: User) -> list[dict[str, Any]]:
    names = _assignee_names(current_user)
    if not names:
        return []

    tasks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    async for t in db.housekeeping_tasks.find(
        {
            "tenant_id": current_user.tenant_id,
            "assigned_to": {"$in": names},
            "status": {"$nin": list(_DONE_TASK_STATUSES)},
        }
    ).sort("created_at", -1).limit(200):
        tid = t.get("id")
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        tasks.append(
            {
                "id": tid,
                "kind": "housekeeping",
                "title": t.get("task_type", "Görev"),
                "room_number": t.get("room_number"),
                "priority": t.get("priority", "normal"),
                "status": t.get("status", "pending"),
                "notes": t.get("notes"),
                "created_at": _sort_key(t.get("created_at")),
            }
        )

    for collection in (db.tasks, db.maintenance_tasks):
        async for t in collection.find(
            {
                "tenant_id": current_user.tenant_id,
                "assigned_to": {"$in": names},
                "status": {"$nin": list(_DONE_TASK_STATUSES)},
            }
        ).sort("created_at", -1).limit(200):
            tid = t.get("id")
            if not tid or tid in seen_ids:
                continue
            # db.tasks holds many departments; keep only maintenance-relevant.
            dept = t.get("department")
            if collection is db.tasks and dept and dept != "maintenance":
                continue
            seen_ids.add(tid)
            tasks.append(
                {
                    "id": tid,
                    "kind": "maintenance",
                    "title": t.get("title") or t.get("task_type") or "Bakım görevi",
                    "room_number": t.get("room_number"),
                    "priority": t.get("priority", "normal"),
                    "status": t.get("status", "pending"),
                    "notes": t.get("description") or t.get("notes"),
                    "created_at": _sort_key(t.get("created_at")),
                }
            )

    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    return tasks


@router.get("/my-tasks")
async def get_my_tasks(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Housekeeping + maintenance tasks assigned to the signed-in person."""
    current_user = await get_current_user(credentials)
    tasks = await _collect_my_tasks(current_user)
    return {
        "tasks": tasks,
        "count": len(tasks),
        "by_kind": {
            "housekeeping": len([t for t in tasks if t["kind"] == "housekeeping"]),
            "maintenance": len([t for t in tasks if t["kind"] == "maintenance"]),
        },
    }


# ── 3. "Bugünkü İşler" — personal today digest ──────────────────────────────


@router.get("/today")
async def get_today_digest(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Personal daily digest for any staff member (non-manager friendly).

    Combines the person's own open tasks, unread feed count, and (only when
    permitted) their pending-approval count into one lightweight summary.
    """
    current_user = await get_current_user(credentials)

    tasks = await _collect_my_tasks(current_user)

    names = _assignee_names(current_user)
    notif_unread = await db.notifications.count_documents(
        {
            "$or": [
                {"user_id": current_user.id},
                {"tenant_id": current_user.tenant_id, "user_id": None},
            ],
            "read": False,
        }
    )
    alert_unread = await db.alerts.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"assigned_to": {"$in": names}} if names else {"assigned_to": "__none__"},
                {"assigned_to": None},
            ],
            "status": "unread",
        }
    )

    pending_approvals = 0
    if _can(current_user, "manage_approvals"):
        pending_approvals += await db.approvals.count_documents(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        )
        pending_approvals += await db.approval_requests.count_documents(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        )
    if _can(current_user, "view_hr"):
        pending_approvals += await db.leave_requests.count_documents(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        )
        pending_approvals += await db.shift_swap_requests.count_documents(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        )

    urgent_tasks = [t for t in tasks if t.get("priority") in ("urgent", "high")]

    return {
        "date": datetime.now(UTC).date().isoformat(),
        "open_tasks": len(tasks),
        "urgent_tasks": len(urgent_tasks),
        "unread_feed": notif_unread + alert_unread,
        "pending_approvals": pending_approvals,
        "tasks_preview": tasks[:5],
    }


# ── 4. "Onaylarım" — unified approvals (finance + HR) ───────────────────────


@router.get("/approvals")
async def get_unified_approvals(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Merge finance/general approvals with the separate HR approval streams.

    Each category is only included when the caller holds the matching view
    permission (the underlying approve/reject endpoints still enforce their
    own RBAC). Nothing here grants access that the user does not already have.
    """
    current_user = await get_current_user(credentials)

    categories: list[dict[str, Any]] = []
    total = 0

    if _can(current_user, "manage_approvals"):
        finance_items: list[dict[str, Any]] = []
        # `approval` (PMS approvals collection) and `approval_request` (analytics
        # approval_requests collection) are BOTH surfaced under the "finance"
        # category, but they expose DIFFERENT approve/reject endpoints. The item
        # `kind` carries which one so the action can route to the correct
        # endpoint without weakening any RBAC.
        async for a in db.approvals.find(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        ).sort("request_date", -1).limit(200):
            finance_items.append(
                {
                    "id": a.get("id"),
                    "kind": "approval",
                    "title": a.get("title") or a.get("type") or "Onay",
                    "requested_by": a.get("requested_by") or a.get("created_by"),
                    "amount": a.get("amount"),
                    "priority": a.get("priority", "normal"),
                    "status": a.get("status", "pending"),
                    "created_at": _sort_key(a.get("request_date") or a.get("created_at")),
                }
            )
        async for a in db.approval_requests.find(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        ).sort("created_at", -1).limit(200):
            finance_items.append(
                {
                    "id": a.get("id"),
                    "kind": "approval_request",
                    "title": a.get("title") or a.get("type") or "Onay",
                    "requested_by": a.get("requested_by") or a.get("created_by"),
                    "amount": a.get("amount"),
                    "priority": a.get("priority", "normal"),
                    "status": a.get("status", "pending"),
                    "created_at": _sort_key(a.get("created_at")),
                }
            )
        finance_items.sort(key=lambda x: x["created_at"], reverse=True)
        total += len(finance_items)
        categories.append(
            {"key": "finance", "label": "Finans", "items": finance_items, "count": len(finance_items)}
        )

    if _can(current_user, "view_hr"):
        hr_items: list[dict[str, Any]] = []
        # Leave approval is a 2-stage chain (pending -> dept_approved -> approved).
        # Both not-yet-final stages are surfaced so a manager can advance the
        # request the rest of the way from mobile; the item `status` tells the
        # client which decision to send next.
        async for lr in db.leave_requests.find(
            {
                "tenant_id": current_user.tenant_id,
                "status": {"$in": ["pending", "dept_approved"]},
            }
        ).sort("created_at", -1).limit(200):
            hr_items.append(
                {
                    "id": lr.get("id"),
                    "kind": "leave",
                    "title": lr.get("leave_type") or "İzin talebi",
                    "requested_by": lr.get("staff_name") or lr.get("staff_id"),
                    "priority": "normal",
                    "status": lr.get("status", "pending"),
                    "created_at": _sort_key(lr.get("created_at")),
                }
            )
        async for sw in db.shift_swap_requests.find(
            {"tenant_id": current_user.tenant_id, "status": "pending"}
        ).sort("requested_at", -1).limit(200):
            hr_items.append(
                {
                    "id": sw.get("id"),
                    "kind": "shift_swap",
                    "title": "Vardiya değişimi",
                    "requested_by": sw.get("from_staff_name") or sw.get("from_staff_id"),
                    "priority": "normal",
                    "status": sw.get("status", "pending"),
                    "target_consent_status": sw.get("target_consent_status", "pending"),
                    "created_at": _sort_key(sw.get("requested_at") or sw.get("created_at")),
                }
            )
        hr_items.sort(key=lambda x: x["created_at"], reverse=True)
        total += len(hr_items)
        categories.append(
            {"key": "hr", "label": "İnsan Kaynakları", "items": hr_items, "count": len(hr_items)}
        )

    return {"categories": categories, "total": total}
