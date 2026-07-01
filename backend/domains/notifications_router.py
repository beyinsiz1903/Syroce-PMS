"""
Notifications Router — Bildirim endpoint'leri
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


def _role_value(user: User) -> str:
    """Return the user's role as a plain string (Enum-tolerant)."""
    return getattr(user.role, "value", str(user.role))


def _visibility_filter(user: User) -> dict:
    """Filter clause that respects optional ``target_roles`` targeting.

    Notifications without ``target_roles`` (or with an empty list) stay
    tenant-broadcast — visible to every user, preserving the historical
    behaviour. Notifications that DO carry ``target_roles`` are limited
    to the listed roles. This is what lets compliance/manager-only
    alarms (e.g. KVKK ID-photo burst alerts written by
    ``workers/id_photo_view_alert.py``) avoid leaking to clerks and
    front-desk staff while still using the shared notification bell.
    """
    return {
        "$or": [
            {"target_roles": {"$exists": False}},
            {"target_roles": None},
            {"target_roles": {"$size": 0}},
            {"target_roles": _role_value(user)},
        ],
    }


@router.get("/list")
async def list_notifications(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """List notifications for the current user."""
    tenant_id = current_user.tenant_id
    visibility = _visibility_filter(current_user)
    notifications = (
        await db.notifications.find(
            {"tenant_id": tenant_id, **visibility},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    # Normalize legacy is_read field to read
    for n in notifications:
        if "read" not in n and "is_read" in n:
            n["read"] = n.pop("is_read")

    unread_count = await db.notifications.count_documents({"tenant_id": tenant_id, "read": {"$ne": True}, **visibility})

    return {"notifications": notifications, "unread_count": unread_count}


@router.put("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
):
    """Bildirimi okundu olarak isaretle.

    Authz: kullanıcı yalnız ``_visibility_filter`` kapsamına giren
    bildirimleri okundu yapabilir; yani manager-only KVKK alarmlarını
    bir clerk işaretleyemez (görmediği bildirimleri suppress edemez).
    """
    tenant_id = current_user.tenant_id
    visibility = _visibility_filter(current_user)
    result = await db.notifications.update_one(
        {"tenant_id": tenant_id, "id": notification_id, **visibility},
        {"$set": {"read": True, "read_at": datetime.now(UTC).isoformat()}, "$unset": {"is_read": ""}},
    )
    return {"ok": True, "modified": getattr(result, "modified_count", 0)}


@router.put("/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
):
    """Tum bildirimleri okundu olarak isaretle.

    Authz: yalnız kullanıcının görme yetkisi bulunan bildirimleri
    güncelle — manager-only uyarılar diğer rollerin toplu işaretiyle
    bastırılamaz.
    """
    tenant_id = current_user.tenant_id
    visibility = _visibility_filter(current_user)
    now = datetime.now(UTC).isoformat()
    result = await db.notifications.update_many(
        {"tenant_id": tenant_id, "read": {"$ne": True}, **visibility},
        {"$set": {"read": True, "read_at": now}, "$unset": {"is_read": ""}},
    )
    return {"ok": True, "modified": getattr(result, "modified_count", 0)}
