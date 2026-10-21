"""Version-to-version changes and acknowledged, in-app document distribution."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from core.booking_atomicity import with_resource_locks
from core.entitlements.enforcement import require_feature
from core.mice_operations import can_manage_operations
from core.security import get_current_user
from core.spa_mice_authz import require_mice_ops
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(dependencies=[Depends(require_feature("mice", "banquet_operations"))])


def snapshot_changes(before, after, path=""):
    """Compare saved commercial content, ignoring generation-time metadata."""
    ignored = {"document", "updated_at", "created_at", "signature", "signature_request"}
    if isinstance(before, dict) and isinstance(after, dict):
        return [change for key in sorted(set(before) | set(after)) if key not in ignored
                for change in snapshot_changes(before.get(key), after.get(key), f"{path}.{key}".strip('.'))]
    if isinstance(before, list) and isinstance(after, list):
        return [change for index in range(max(len(before), len(after)))
                for change in snapshot_changes(before[index] if index < len(before) else None, after[index] if index < len(after) else None, f"{path}[{index + 1}]")]
    return [] if before == after else [{"field": path, "before": before, "after": after}]


@router.get("/events/{event_id}/document-changes")
async def document_changes(event_id: str, to_id: str = Query(...), from_id: str | None = None, current_user: User = Depends(get_current_user)):
    event = await get_system_db().mice_events.find_one({"tenant_id": current_user.tenant_id, "id": event_id}, {"_id": 0})
    history = (event or {}).get("document_history") or []
    target = next((d for d in history if d["id"] == to_id), None)
    previous = next((d for d in history if d["id"] == from_id), None) if from_id else next((d for d in history if target and d["number"] == target["number"] - 1), None)
    if not target or (from_id and not previous):
        raise HTTPException(404, "Belge sürümü bulunamadı")
    return {"from_number": previous["number"] if previous else None, "to_number": target["number"],
            "changes": snapshot_changes(previous["snapshot"] if previous else {}, target["snapshot"]),
            "document_id": to_id, "can_acknowledge": event.get("active_document_id") == to_id and any(d["document_id"] == to_id and d["user_id"] == current_user.id and not d.get("acknowledged_at") for d in event.get("document_deliveries") or []),
            "deliveries": [d for d in (event.get("document_deliveries") or []) if d["document_id"] == to_id and (can_manage_operations(current_user) or d["user_id"] == current_user.id)]}


@router.post("/events/{event_id}/documents/{document_id}/distribute")
async def distribute_document(event_id: str, document_id: str, current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_sales"))):
    require_mice_ops(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    async def distribute(session):
        event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, session=session)
        doc = next((d for d in (event or {}).get("document_history") or [] if d["id"] == document_id), None)
        if not doc:
            raise HTTPException(404, "Belge bulunamadı")
        if event.get("active_document_id") != document_id:
            raise HTTPException(409, "Yalnız güncel belge departmanlara dağıtılabilir")
        existing = event.get("document_deliveries") or []
        targets = {(t["department"], t["owner_user_id"]) for t in event.get("operations_tasks") or [] if t.get("owner_user_id") and t["status"] != "cancelled"}
        if not targets:
            raise HTTPException(422, "Önce departman görevlerine sorumlu personel hesabı atayın")
        now = datetime.now(UTC).isoformat()
        for department, owner in sorted(targets):
            if any(d["document_id"] == document_id and d["department"] == department and d["user_id"] == owner for d in existing):
                continue
            delivery = {"id": str(uuid.uuid4()), "document_id": document_id, "department": department, "user_id": owner, "sent_at": now, "sent_by": current_user.username, "acknowledged_at": None}
            existing.append(delivery)
            nid = f"mice-document:{delivery['id']}"
            await db.notifications.insert_one({"_id": nid, "id": nid, "tenant_id": tid, "type": "mice_document", "title": f"Banket BEO v{doc['number']}: yeni belge", "message": "Değişiklik dökümünü inceleyip teslim aldığınızı onaylayın.", "target_roles": [], "target_user_ids": [owner], "event_id": event_id, "document_id": document_id, "read": False, "created_at": now, "action_url": f"/app/mice?event_id={event_id}"}, session=session)
        await db.mice_events.update_one({"tenant_id": tid, "id": event_id}, {"$set": {"document_deliveries": existing}}, session=session)
        return {"deliveries": [d for d in existing if d["document_id"] == document_id], "notice": "Uygulama içi bildirim oluşturuldu; e-posta gönderilmedi."}
    return await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("event", event_id)], callback=distribute)


@router.post("/events/{event_id}/documents/{document_id}/acknowledge")
async def acknowledge_document(event_id: str, document_id: str, current_user: User = Depends(get_current_user)):
    db, tid = get_system_db(), current_user.tenant_id
    async def accept(session):
        event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, session=session)
        if not event or event.get("active_document_id") != document_id:
            raise HTTPException(409, "Belge güncel değil; son sürümü inceleyin")
        deliveries = event.get("document_deliveries") or []
        own = [d for d in deliveries if d["document_id"] == document_id and d["user_id"] == current_user.id]
        if not own:
            raise HTTPException(403, "Bu belge size dağıtılmamış")
        for row in own:
            row["acknowledged_at"] = row.get("acknowledged_at") or datetime.now(UTC).isoformat()
        await db.mice_events.update_one({"tenant_id": tid, "id": event_id}, {"$set": {"document_deliveries": deliveries}}, session=session)
        return {"ok": True}
    return await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("event", event_id)], callback=accept)
