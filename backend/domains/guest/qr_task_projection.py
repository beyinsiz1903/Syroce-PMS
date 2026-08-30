"""Project room QR requests into the shared staff-task workflow.

The QR guest experience has two request collections for backwards
compatibility (``room_qr_requests`` and ``qr_requests``).  Operations must not
care which guest form produced a request, so this module exposes one
idempotent task projection and keeps status/result updates synchronized back
to the source request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.tenant_db import get_db_for_tenant

SOURCE_COLLECTIONS = ("room_qr_requests", "qr_requests")

QR_TO_TASK_DEPARTMENT = {
    "rooms": "housekeeping",
    "minibar": "housekeeping",
    "laundry": "housekeeping",
    "technical": "maintenance",
    "fnb": "fb",
    "spa": "frontdesk",
    "transportation": "frontdesk",
    "other": "frontdesk",
}

SOURCE_TO_TASK_STATUS = {
    "new": "pending",
    "assigned": "pending",
    "in_progress": "in_progress",
    "completed": "completed",
    "cancelled": "cancelled",
}


def task_id_for_request(request_id: str) -> str:
    return f"guest-qr:{request_id}"


def task_document(request_doc: dict[str, Any], source_collection: str) -> dict[str, Any]:
    request_id = str(request_doc.get("_id") or request_doc.get("id") or "")
    snapshot = request_doc.get("catalogue_snapshot") or {}
    return {
        "id": task_id_for_request(request_id),
        "tenant_id": request_doc.get("tenant_id"),
        "task_type": "guest_request",
        "department": QR_TO_TASK_DEPARTMENT.get(request_doc.get("department"), "frontdesk"),
        "title": request_doc.get("title") or f"Misafir talebi — Oda {request_doc.get('room_number') or '?'}",
        "room_id": request_doc.get("room_id"),
        "room_number": request_doc.get("room_number"),
        "priority": request_doc.get("priority") or "normal",
        "description": request_doc.get("description") or None,
        "assigned_to": request_doc.get("assigned_to") or None,
        "status": SOURCE_TO_TASK_STATUS.get(request_doc.get("status"), "pending"),
        "source": "guest_qr",
        "source_collection": source_collection,
        "source_request_id": request_id,
        "booking_id": request_doc.get("booking_id"),
        "request_reference": request_doc.get("request_reference"),
        "estimated_minutes": snapshot.get("estimated_minutes_snapshot"),
        "created_at": request_doc.get("created_at") or datetime.now(UTC),
        "updated_at": request_doc.get("updated_at") or datetime.now(UTC),
        "completed_at": request_doc.get("completed_at"),
    }


async def project_request(request_doc: dict[str, Any], source_collection: str) -> dict[str, Any]:
    """Create/update exactly one staff task for a QR request."""
    if source_collection not in SOURCE_COLLECTIONS:
        raise ValueError("unsupported QR request collection")
    task = task_document(request_doc, source_collection)
    if not task["tenant_id"] or not task["source_request_id"]:
        raise ValueError("QR request is missing tenant/id")
    tenant_db = get_db_for_tenant(task["tenant_id"])
    await tenant_db["staff_tasks"].update_one(
        {"tenant_id": task["tenant_id"], "id": task["id"]},
        {
            "$set": task,
            "$setOnInsert": {"created_by": "guest_qr"},
        },
        upsert=True,
    )
    return task


async def record_new_request(request_doc: dict[str, Any], source_collection: str) -> dict[str, Any]:
    """Project a newly-created request and add a PII-free operations event."""
    task = await project_request(request_doc, source_collection)
    try:
        from modules.event_system.event_bus import EventBus

        await EventBus().publish(
            task["tenant_id"],
            "guest_request_created",
            {
                "task_id": task["id"],
                "request_id": task["source_request_id"],
                "room_number": task.get("room_number"),
                "department": task.get("department"),
                "priority": task.get("priority"),
            },
            property_id=request_doc.get("property_id"),
        )
    except Exception:
        # Task persistence is authoritative. The dashboard event is a
        # best-effort operational projection and must never lose a guest request.
        pass
    return task


async def reconcile_tenant_requests(tenant_id: str, *, limit_per_source: int = 500) -> int:
    """Backfill requests that do not yet have a shared task projection.

    Current create/update paths project synchronously.  The read-side repair is
    therefore intentionally insert-only: opening the Tasks page must not write
    hundreds of already-converged records on every refresh.
    """
    projected = 0
    tenant_db = get_db_for_tenant(tenant_id)
    existing_ids: set[str] = set()
    existing_cursor = tenant_db["staff_tasks"].find(
        {"tenant_id": tenant_id, "source": "guest_qr"},
        {"id": 1},
    )
    async for existing in existing_cursor:
        if existing.get("id"):
            existing_ids.add(str(existing["id"]))

    for collection in SOURCE_COLLECTIONS:
        cursor = tenant_db[collection].find({"tenant_id": tenant_id}).sort("created_at", -1).limit(limit_per_source)
        async for request_doc in cursor:
            request_id = str(request_doc.get("_id") or request_doc.get("id") or "")
            if not request_id or task_id_for_request(request_id) in existing_ids:
                continue
            await project_request(request_doc, collection)
            existing_ids.add(task_id_for_request(request_id))
            projected += 1
    return projected


async def find_source_request(tenant_id: str, request_id: str) -> tuple[str, dict[str, Any]] | None:
    tenant_db = get_db_for_tenant(tenant_id)
    for collection in SOURCE_COLLECTIONS:
        doc = await tenant_db[collection].find_one({"tenant_id": tenant_id, "_id": request_id})
        if doc:
            return collection, doc
    return None


def _source_status(task_status: str, assigned_to: str | None) -> str:
    if task_status == "pending":
        return "assigned" if assigned_to else "new"
    return task_status


async def update_qr_task(
    task: dict[str, Any],
    updates: dict[str, Any],
    *,
    actor_id: str,
    actor_name: str,
) -> dict[str, Any]:
    """Apply a task update to its QR source and optionally reply to the guest."""
    tenant_id = task["tenant_id"]
    request_id = task.get("source_request_id")
    source_collection = task.get("source_collection")
    if source_collection not in SOURCE_COLLECTIONS or not request_id:
        raise ValueError("task is not linked to a QR request")

    tenant_db = get_db_for_tenant(tenant_id)
    source = await tenant_db[source_collection].find_one(
        {"tenant_id": tenant_id, "_id": request_id}
    )
    if not source:
        raise LookupError("QR request source not found")

    now = datetime.now(UTC)
    source_set: dict[str, Any] = {"updated_at": now}
    history: dict[str, Any] = {"at": now, "by": actor_name, "actor_id": actor_id}

    assigned_to = updates.get("assigned_to", source.get("assigned_to"))
    if "assigned_to" in updates:
        source_set["assigned_to"] = assigned_to or None
        history["assigned_to"] = assigned_to or None
    if "department" in updates:
        # The task-side department vocabulary is deliberately not copied back;
        # the canonical QR routing department remains stable for audit/reporting.
        pass
    if "priority" in updates:
        source_set["priority"] = updates["priority"]
        history["priority"] = updates["priority"]
    if "status" in updates:
        source_status = _source_status(updates["status"], assigned_to)
        source_set["status"] = source_status
        history["status"] = source_status
        if source_status == "completed":
            source_set["completed_at"] = now
        elif source.get("completed_at"):
            source_set["completed_at"] = None

    resolution = str(updates.get("resolution_note") or "").strip()
    if resolution:
        history["note"] = resolution
        source_set["resolution_note"] = resolution
        source_set["resolved_by"] = actor_name

    await tenant_db[source_collection].update_one(
        {"tenant_id": tenant_id, "_id": request_id},
        {"$set": source_set, "$push": {"status_history": history}},
    )

    if resolution:
        from domains.guest.messaging import guest_requests as guest_messages

        property_id = source.get("property_id")
        if not property_id and source.get("room_id"):
            room = await tenant_db["rooms"].find_one(
                {"tenant_id": tenant_id, "id": source["room_id"]},
                {"property_id": 1},
            )
            property_id = (room or {}).get("property_id")
        await guest_messages.add_guest_message(
            tenant_id=tenant_id,
            property_id=property_id,
            room_id=source.get("room_id"),
            room_number=source.get("room_number"),
            sender_type="staff",
            body=resolution,
            booking_id=source.get("booking_id"),
            sender_user_id=actor_id,
            sender_name=actor_name,
            request_id=request_id,
        )
        await guest_messages.emit_guest_requests_ping(tenant_id, source.get("room_id"))

    if updates.get("status") == "completed":
        try:
            from modules.event_system.event_bus import EventBus

            await EventBus().publish(
                tenant_id,
                "guest_request_completed",
                {
                    "task_id": task["id"],
                    "request_id": request_id,
                    "room_number": source.get("room_number"),
                    "department": task.get("department"),
                },
                user_id=actor_id,
                property_id=source.get("property_id"),
            )
        except Exception:
            pass

    updated_source = {**source, **source_set}
    return await project_request(updated_source, source_collection)
