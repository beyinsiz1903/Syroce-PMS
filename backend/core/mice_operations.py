"""Department-scoped task access and durable in-app handover notices."""
from datetime import UTC, datetime


def can_manage_operations(user):
    raw_role = getattr(user, "role", None)
    role = getattr(raw_role, "value", raw_role)
    return role in {"super_admin", "admin", "supervisor", "sales"}


def can_work_task(user, task):
    if can_manage_operations(user):
        return True
    if task.get("owner_user_id") and task["owner_user_id"] == getattr(user, "id", None):
        return True
    role = getattr(user.role, "value", user.role)
    if role == "housekeeping" and task.get("department") == "housekeeping":
        return True
    return f"mice_ops:{task.get('department')}" in (getattr(user, "granted_permissions", None) or [])


async def task_notice(db, tid, event_id, task, action, session=None, message=None):
    targets = [task["owner_user_id"]] if task.get("owner_user_id") else None
    # Department grants are enforced by the task endpoint. Unassigned notices
    # go only to MICE managers, not every staff member in the property.
    notice_id = f"mice-task:{event_id}:{task['id']}:{action}"
    await db.notifications.update_one({"_id": notice_id, "tenant_id": tid}, {"$setOnInsert": {
        "id": notice_id, "tenant_id": tid, "type": "mice_task", "title": f"Banket görevi: {task['title']}",
        "message": message or f"{task['department']} · Görev atandı", "event_id": event_id, "task_id": task["id"],
        "target_user_ids": targets, "target_roles": [] if targets else ["super_admin", "admin", "supervisor", "sales"],
        "read": False, "created_at": datetime.now(UTC).isoformat(), "action_url": f"/app/mice?event_id={event_id}",
    }}, upsert=True, session=session)
