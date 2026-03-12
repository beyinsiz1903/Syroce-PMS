"""
Event Bus Router — publish, subscribe, replay, status, metrics.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/event-bus", tags=["event-bus"])


@router.get("/status")
async def get_status(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    return await event_bus.get_status()


@router.get("/metrics")
async def get_metrics(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    return await event_bus.get_metrics()


@router.post("/publish")
async def publish_event(
    event_type: str = Query("test_event"),
    priority: str = Query("normal"),
    current_user: User = Depends(get_current_user),
):
    from modules.event_bus.abstraction import event_bus
    result = await event_bus.publish(
        tenant_id=current_user.tenant_id,
        event_type=event_type,
        payload={"source": "manual", "user_id": current_user.id},
        source="admin_api",
        priority=priority,
    )
    return result


@router.get("/replay")
async def replay_events(
    since: Optional[str] = None,
    event_types: Optional[str] = None,
    limit: int = Query(50, le=500),
    current_user: User = Depends(get_current_user),
):
    from modules.event_bus.abstraction import event_bus
    types = event_types.split(",") if event_types else None
    return await event_bus.replay(current_user.tenant_id, since, types, limit)


@router.get("/replay/summary")
async def replay_summary(current_user: User = Depends(get_current_user)):
    from datetime import datetime, timezone, timedelta
    from core.database import db

    one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    count = await db.event_bus_log.count_documents({
        "tenant_id": current_user.tenant_id,
        "timestamp": {"$gte": one_day_ago},
    })
    pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id, "timestamp": {"$gte": one_day_ago}}},
        {"$group": {
            "_id": "$event_type",
            "count": {"$sum": 1},
            "last_sequence": {"$max": "$sequence"},
        }},
        {"$sort": {"count": -1}},
    ]
    by_type = await db.event_bus_log.aggregate(pipeline).to_list(20)
    return {
        "replayable_events_24h": count,
        "by_type": [{"event_type": r["_id"], "count": r["count"], "last_sequence": r["last_sequence"]} for r in by_type],
    }


@router.get("/channels")
async def get_channels(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    return event_bus.get_channels(current_user.tenant_id)


@router.get("/sessions")
async def get_sessions(current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    return event_bus.get_active_sessions(current_user.tenant_id)


@router.post("/sessions/register")
async def register_session(
    session_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    from modules.event_bus.abstraction import event_bus
    return event_bus.register_session(
        tenant_id=current_user.tenant_id,
        session_id=session_id,
        user_id=current_user.id,
        roles=current_user.roles if hasattr(current_user, "roles") else ["admin"],
    )


@router.post("/sessions/{session_id}/unregister")
async def unregister_session(session_id: str, current_user: User = Depends(get_current_user)):
    from modules.event_bus.abstraction import event_bus
    event_bus.unregister_session(current_user.tenant_id, session_id)
    return {"session_id": session_id, "status": "unregistered"}
