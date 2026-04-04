"""
Notifications Router — Bildirim endpoint'leri
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/list")
async def list_notifications(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """Kullanıcının bildirimlerini listele."""
    tenant_id = current_user.tenant_id
    notifications = await db.notifications.find(
        {"tenant_id": tenant_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    unread_count = await db.notifications.count_documents(
        {"tenant_id": tenant_id, "read": False}
    )

    return {"notifications": notifications, "unread_count": unread_count}


@router.put("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
):
    """Bildirimi okundu olarak isaretle."""
    tenant_id = current_user.tenant_id
    await db.notifications.update_one(
        {"tenant_id": tenant_id, "id": notification_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}
