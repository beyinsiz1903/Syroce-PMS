"""
Event Broadcast / WebSocket Health Router.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

router = APIRouter(prefix="/api/websocket", tags=["websocket"])

_service = None


def _get_service():
    global _service
    if _service is None:
        from modules.event_broadcast.service import EventBroadcastService
        from server import db
        _service = EventBroadcastService(db)
    return _service


@router.get("/health")
async def ws_health(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    metrics = await svc.get_metrics(current_user.tenant_id)
    sessions = svc.get_active_sessions(current_user.tenant_id)
    return {"health": "ok", "metrics": metrics, "sessions": sessions}


class RegisterSessionReq(BaseModel):
    session_id: str
    roles: list = []
    property_ids: list = []


@router.post("/sessions/register")
async def register_session(req: RegisterSessionReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    svc = _get_service()
    return svc.register_session(
        current_user.tenant_id, req.session_id, current_user.id,
        req.roles or [current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)],
        req.property_ids,
    )


@router.delete("/sessions/{session_id}")
async def unregister_session(session_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    from fastapi import HTTPException
    svc = _get_service()
    tenant_sessions = getattr(svc, "_sessions", {}).get(current_user.tenant_id, {}) if hasattr(svc, "_sessions") else {}
    sess = tenant_sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    is_admin = str(getattr(current_user.role, "value", current_user.role)) in ("super_admin", "admin", "owner")
    if not is_admin and sess.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="cannot unregister another user's session")
    svc.unregister_session(current_user.tenant_id, session_id)
    return {"success": True}


class PublishEventReq(BaseModel):
    event_type: str
    payload: dict = {}
    property_id: str | None = None


@router.post("/publish")
async def publish_event(req: PublishEventReq, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    svc = _get_service()
    return await svc.publish(
        current_user.tenant_id, req.event_type, req.payload, req.property_id, source=current_user.id,
    )


@router.get("/replay")
async def replay_events(
    since: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    svc = _get_service()
    events = await svc.get_replay(current_user.tenant_id, since, limit)
    return {"events": events, "count": len(events)}
