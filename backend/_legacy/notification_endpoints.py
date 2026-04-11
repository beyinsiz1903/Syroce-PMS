from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime, timezone
import uuid

from server import get_current_user, User, db


class PushPlatform(str, Enum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"
    DESKTOP = "desktop"


class SubscriptionPayload(BaseModel):
    endpoint: str
    public_key: str = Field(..., description="VAPID key or device token")
    auth_key: str
    platform: PushPlatform = PushPlatform.WEB
    role: Optional[str] = None
    locale: Optional[str] = None
    device_info: Dict[str, Any] = Field(default_factory=dict)


class TestNotification(BaseModel):
    title: str
    body: str
    data: Dict[str, Any] = Field(default_factory=dict)
    subscription_id: Optional[str] = None


notification_router = APIRouter(prefix="/notifications", tags=["notifications"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != "_id"}
    return doc


@notification_router.post("/subscribe")
async def subscribe_push(
    payload: SubscriptionPayload,
    current_user: User = Depends(get_current_user)
):
    """Register or update a push subscription for the current user."""
    if not payload.endpoint:
        raise HTTPException(status_code=400, detail="Endpoint is required")

    existing = await db.push_subscriptions.find_one({
        "tenant_id": current_user.tenant_id,
        "endpoint": payload.endpoint
    })

    subscription_id = existing.get("id") if existing else str(uuid.uuid4())

    doc = {
        "id": subscription_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "role": payload.role or "unknown",
        "endpoint": payload.endpoint,
        "public_key": payload.public_key,
        "auth_key": payload.auth_key,
        "platform": payload.platform.value,
        "locale": payload.locale or "en",
        "device_info": payload.device_info,
        "active": True,
        "updated_at": _now()
    }

    if existing:
        await db.push_subscriptions.update_one(
            {"id": subscription_id},
            {"$set": doc}
        )
    else:
        doc["created_at"] = _now()
        await db.push_subscriptions.insert_one(doc)

    return {"success": True, "subscription": _serialize(doc)}


@notification_router.delete("/subscribe/{subscription_id}")
async def unsubscribe_push(
    subscription_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.push_subscriptions.update_one(
        {"id": subscription_id, "tenant_id": current_user.tenant_id},
        {"$set": {"active": False, "updated_at": _now()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"success": True, "subscription_id": subscription_id}


@notification_router.get("/subscriptions")
async def list_subscriptions(
    role: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    query = {"tenant_id": current_user.tenant_id, "user_id": current_user.id}
    if role:
        query["role"] = role
    items = await db.push_subscriptions.find(query, {"_id": 0}).to_list(100)
    return {"items": items, "count": len(items)}


@notification_router.post("/send-test")
async def send_test_notification(
    payload: TestNotification,
    current_user: User = Depends(get_current_user)
):
    """Store a test notification event (actual push delivery handled by worker)."""
    if payload.subscription_id:
        subscription = await db.push_subscriptions.find_one({
            "tenant_id": current_user.tenant_id,
            "id": payload.subscription_id,
            "active": True
        })
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        targets: List[dict] = [subscription]
    else:
        targets = await db.push_subscriptions.find({
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "active": True
        }).to_list(20)

    if not targets:
        raise HTTPException(status_code=400, detail="No active subscriptions to send")

    event = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "title": payload.title,
        "body": payload.body,
        "data": payload.data,
        "target_count": len(targets),
        "status": "queued",
        "created_at": _now()
    }
    await db.notification_events.insert_one(event)

    return {"success": True, "event": _serialize(event)}
