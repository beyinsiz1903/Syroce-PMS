"""
PMS / Notifications Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from domains.pms.pos_fnb.schemas import Alert
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v100 DW

logger = logging.getLogger(__name__)

DEFAULT_PUSH_CHANNELS = ["reservations", "housekeeping", "maintenance", "system"]

# Per-user micro-cache for /notifications/list. The dashboard polls this every
# few seconds; the underlying Mongo query (no index on user_id+created_at) costs
# ~1s on the first call. A 10-second TTL keeps the UI responsive while cutting
# DB load by ~10x and stays well below "user perceives stale" threshold.
_NOTIF_LIST_CACHE: dict[tuple[str, bool, int], tuple[float, dict]] = {}
_NOTIF_LIST_TTL_SEC = 10.0

# Index creation guard: serialize first-request concurrency with a Lock and
# track success vs transient failure separately so transient errors are retried
# (with backoff) instead of being permanently suppressed.
_NOTIF_INDEX_LOCK = asyncio.Lock()
_NOTIF_INDEX_CREATED = False
_NOTIF_INDEX_LAST_ATTEMPT = 0.0
_NOTIF_INDEX_RETRY_BACKOFF_SEC = 60.0  # after a failure, wait at least 60s before retrying


async def _ensure_notif_indexes() -> None:
    """Create compound indexes the first time the notifications endpoint is hit.

    - Idempotent: Mongo's create_index is a no-op if the index already exists.
    - Concurrency-safe: a single asyncio.Lock prevents the first 50 concurrent
      requests after a fresh start from all calling create_index simultaneously.
    - Transient-failure resilient: on error we backoff for 60s rather than
      permanently disabling retries (which would leave the table un-indexed
      until the next process restart).
    """
    global _NOTIF_INDEX_CREATED, _NOTIF_INDEX_LAST_ATTEMPT
    if _NOTIF_INDEX_CREATED:
        return
    now = time.monotonic()
    if (now - _NOTIF_INDEX_LAST_ATTEMPT) < _NOTIF_INDEX_RETRY_BACKOFF_SEC:
        return  # last attempt failed recently, don't hammer Mongo
    async with _NOTIF_INDEX_LOCK:
        if _NOTIF_INDEX_CREATED:  # double-checked locking
            return
        _NOTIF_INDEX_LAST_ATTEMPT = time.monotonic()
        try:
            await db.notifications.create_index(
                [("user_id", 1), ("created_at", -1)], background=True
            )
            await db.notifications.create_index(
                [("tenant_id", 1), ("user_id", 1), ("created_at", -1)], background=True
            )
            _NOTIF_INDEX_CREATED = True
            logger.info("notifications: ensured (user_id, created_at) compound indexes")
        except Exception as exc:
            # Stays False so the next request (after backoff) retries.
            logger.warning(
                "notifications: index creation failed (will retry in %ss): %s",
                int(_NOTIF_INDEX_RETRY_BACKOFF_SEC), exc,
            )


async def _collect_push_devices(
    tenant_id: str,
    user_ids: list[str] | None = None,
    departments: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve push-enabled devices for the given audience."""
    query: dict[str, Any] = {'tenant_id': tenant_id, 'push_token': {'$exists': True, '$ne': None}}
    or_clauses: list[dict[str, Any]] = []
    if user_ids:
        or_clauses.append({'user_id': {'$in': user_ids}})
    if departments:
        or_clauses.append({'departments': {'$in': departments}})
    if or_clauses:
        query['$or'] = or_clauses
    return await db.push_devices.find(query, {'_id': 0}).to_list(2000)


async def _simulate_push_delivery(
    devices: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Stub delivery channel — records intent without actually sending."""
    deliveries = []
    for d in devices:
        deliveries.append({
            'device_id': d.get('device_id'),
            'user_id': d.get('user_id'),
            'platform': d.get('platform'),
            'status': 'queued',
            'notification_id': payload.get('id'),
        })
    return deliveries


async def _record_push_log(
    tenant_id: str,
    payload: dict[str, Any],
    deliveries: list[dict[str, Any]],
    sent_by: str,
) -> None:
    """Persist a delivery audit row for the push notification batch."""
    try:
        await db.push_notification_logs.insert_one({
            'tenant_id': tenant_id,
            'notification_id': payload.get('id'),
            'sent_by': sent_by,
            'deliveries': deliveries,
            'queued_at': datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.exception('[push] failed to persist delivery log')

router = APIRouter(prefix="/api", tags=["PMS / Notifications"])


# ── Inline Models ──

class NotificationPreferenceRequest(BaseModel):
    notification_type: str
    enabled: bool
    channels: list[str] = ['in_app']  # in_app, email, sms, push


class SystemAlertRequest(BaseModel):
    type: str
    title: str
    message: str
    priority: str = "normal"
    target_roles: list[str] | None = None


@router.post("/notifications/send-push")
async def send_push_notification(notif_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    channels = notif_data.get('channels', ['in_app', 'push'])
    target_user_ids = notif_data.get('user_ids')
    if notif_data.get('user_id') and not target_user_ids:
        target_user_ids = [notif_data['user_id']]
    target_departments = notif_data.get('departments')

    payload = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': notif_data['title'],
        'body': notif_data['body'],
        'type': notif_data.get('type', 'info'),
        'priority': notif_data.get('priority', 'normal'),
        'action_url': notif_data.get('action_url'),
        'metadata': notif_data.get('metadata', {}),
        'channels': channels,
        'user_ids': target_user_ids,
        'departments': target_departments,
        'sent_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.id
    }

    if 'in_app' in channels:
        in_app_notification = {
            **payload,
            'user_id': target_user_ids[0] if target_user_ids and len(target_user_ids) == 1 else None,
            'department': target_departments,
            'read': False
        }
        await db.notifications.insert_one(in_app_notification)

    deliveries: list[dict] = []
    if 'push' in channels:
        devices = await _collect_push_devices(
            tenant_id=current_user.tenant_id,
            user_ids=target_user_ids,
            departments=target_departments
        )
        deliveries = await _simulate_push_delivery(devices, payload)

        # V3 — Syroce mobil: in addition to the legacy simulated/in-app
        # delivery audit, fire a real Expo Push so any registered Expo
        # mobile clients in the audience receive an OS-level notification.
        # Best-effort and non-blocking. The helper reads the V3 collection
        # `db.push_device_tokens`, so legacy `db.push_devices` rows above
        # remain untouched (web/admin simulation path).
        try:
            from services.expo_push import fire_and_forget_expo_push
            fire_and_forget_expo_push(
                current_user.tenant_id,
                title=payload['title'],
                body=payload['body'],
                data={
                    'type': payload.get('type', 'info'),
                    'notification_id': payload['id'],
                    'action_url': payload.get('action_url'),
                    **(payload.get('metadata') or {}),
                },
                user_ids=target_user_ids,
                departments=target_departments,
                priority='high' if payload.get('priority') in ('high', 'urgent') else 'default',
            )
        except Exception:
            logger.exception('[push] expo dispatch failed for admin broadcast')

    await db.push_notifications.insert_one({
        **payload,
        'target_count': len(deliveries),
    })
    await _record_push_log(current_user.tenant_id, payload, deliveries, current_user.id)

    return {
        'success': True,
        'notification_id': payload['id'],
        'queued': len(deliveries),
        'channels': channels
    }




@router.post("/notifications/push/register")
async def register_push_device(device_payload: dict, current_user: User = Depends(get_current_user)):
    device_id = device_payload.get('device_id')
    push_token = device_payload.get('push_token')
    if not device_id or not push_token:
        raise HTTPException(status_code=400, detail="device_id and push_token are required")

    subscriptions = device_payload.get('subscriptions') or device_payload.get('channels') or DEFAULT_PUSH_CHANNELS
    departments = device_payload.get('departments') or ([current_user.role] if current_user.role else [])

    device_doc = {
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.id,
        'device_id': device_id,
        'device_name': device_payload.get('device_name'),
        'platform': device_payload.get('platform', 'web'),
        'push_token': push_token,
        'app_version': device_payload.get('app_version'),
        'os_version': device_payload.get('os_version'),
        'user_agent': device_payload.get('user_agent'),
        'timezone': device_payload.get('timezone'),
        'subscriptions': subscriptions,
        'departments': departments,
        'capabilities': device_payload.get('capabilities', {}),
        'updated_at': datetime.now(UTC).isoformat(),
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.push_device_tokens.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id,
            'device_id': device_id
        },
        {'$set': device_doc},
        upsert=True
    )

    return {
        'success': True,
        'device_id': device_id,
        'subscriptions': subscriptions
    }




@router.post("/notifications/push/unregister")
async def unregister_push_device(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """V3 (round 7): explicit unregister so logout / account switch can
    remove a device's Expo push token instead of letting it linger in
    `push_device_tokens` until the next register call. Without this:
      * a logged-out phone keeps receiving notifications meant for the
        previous user (privacy + delivery duplication)
      * a single device row can keep firing for both A and B if the
        device_id collides
    Identifies the row by (tenant_id, user_id, device_id) — i.e. the
    same composite key `register_push_device` upserts on. Optional
    `push_token` is also accepted as a fallback when the caller no
    longer has the device_id (e.g. permission was revoked) so we can
    still prune the stored token.
    """
    device_id = payload.get('device_id')
    push_token = payload.get('push_token')
    if not device_id and not push_token:
        raise HTTPException(
            status_code=400,
            detail="device_id or push_token is required",
        )
    query: dict[str, Any] = {
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.id,
    }
    if device_id:
        query['device_id'] = device_id
    elif push_token:
        query['push_token'] = push_token
    result = await db.push_device_tokens.delete_many(query)
    return {'success': True, 'removed': result.deleted_count}


@router.post("/notifications/push/subscriptions")
async def update_push_subscriptions(subscription_payload: dict, current_user: User = Depends(get_current_user)):
    channels = subscription_payload.get('channels') or DEFAULT_PUSH_CHANNELS

    await db.push_subscriptions.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id
        },
        {
            '$set': {
                'channels': channels,
                'updated_at': datetime.now(UTC).isoformat()
            }
        },
        upsert=True
    )

    await db.push_device_tokens.update_many(
        {
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id
        },
        {'$set': {'subscriptions': channels}}
    )

    return {'success': True, 'channels': channels}




@router.get("/notifications/push/subscriptions")
async def get_push_subscriptions(current_user: User = Depends(get_current_user)):
    record = await db.push_subscriptions.find_one(
        {'tenant_id': current_user.tenant_id, 'user_id': current_user.id},
        {'_id': 0}
    )
    return {
        'channels': record.get('channels') if record else DEFAULT_PUSH_CHANNELS
    }




@router.get("/notifications/push-status")
async def get_push_status(current_user: User = Depends(get_current_user)):
    # Perf: 3 sıralı sorgu (~3 RTT) → asyncio.gather ile paralel.
    import asyncio
    devices, subscription, last_delivery = await asyncio.gather(
        db.push_device_tokens.find(
            {'tenant_id': current_user.tenant_id, 'user_id': current_user.id},
            {'_id': 0}
        ).sort('updated_at', -1).to_list(20),
        db.push_subscriptions.find_one(
            {'tenant_id': current_user.tenant_id, 'user_id': current_user.id},
            {'_id': 0}
        ),
        db.push_delivery_logs.find(
            {'tenant_id': current_user.tenant_id, 'target_user_ids': {'$in': [current_user.id]}},
            {'_id': 0}
        ).sort('created_at', -1).to_list(1),
    )

    return {
        'enabled': len(devices) > 0,
        'devices': devices,
        'device_count': len(devices),
        'subscriptions': subscription.get('channels') if subscription else DEFAULT_PUSH_CHANNELS,
        'last_delivery': last_delivery[0] if last_delivery else None
    }



@router.get("/notifications/my-notifications")
async def get_my_notifications(current_user: User = Depends(get_current_user)):
    notifications = await db.push_notifications.find({
        '$or': [
            {'user_id': current_user.id},
            {'department': current_user.role}
        ],
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('sent_at', -1).limit(50).to_list(50)

    unread_count = len([n for n in notifications if not n.get('read', False)])

    return {
        'notifications': notifications,
        'unread_count': unread_count,
        'total': len(notifications)
    }


# ============= F&B COMPLETE SUITE — MOVED to domains/hr/router.py =============

# ============= FINANCE INTEGRATION (FINANS MÜDÜRÜ İÇİN) =============



@router.get("/inbox/alerts")
async def get_inbox_alerts(
    status: str | None = None,
    alert_type: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """
    Get all alerts for current user
    - Unified inbox
    - Filter by type, priority, status
    - Role-based alerts
    """
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'assigned_to': current_user.name},
            {'assigned_to': None}  # General alerts
        ]
    }

    if status:
        match_criteria['status'] = status
    if alert_type:
        match_criteria['alert_type'] = alert_type
    if priority:
        match_criteria['priority'] = priority

    alerts = []
    async for alert in db.alerts.find(match_criteria).sort('created_at', -1).limit(limit):
        alerts.append({
            'id': alert.get('id'),
            'alert_type': alert.get('alert_type'),
            'priority': alert.get('priority'),
            'title': alert.get('title'),
            'description': alert.get('description'),
            'source_module': alert.get('source_module'),
            'status': alert.get('status'),
            'action_url': alert.get('action_url'),
            'created_at': alert.get('created_at')
        })

    # Count by status
    unread_count = await db.alerts.count_documents({**match_criteria, 'status': 'unread'})

    return {
        'alerts': alerts,
        'total_count': len(alerts),
        'unread_count': unread_count,
        'filters_applied': {
            'status': status,
            'alert_type': alert_type,
            'priority': priority
        }
    }




@router.post("/inbox/alerts")
async def create_alert(
    alert_type: str,
    priority: str,
    title: str,
    description: str,
    source_module: str,
    source_id: str | None = None,
    assigned_to: str | None = None,
    action_url: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Create a new alert"""
    alert = Alert(
        tenant_id=current_user.tenant_id,
        alert_type=alert_type,
        priority=priority,
        title=title,
        description=description,
        source_module=source_module,
        source_id=source_id,
        assigned_to=assigned_to,
        action_url=action_url
    )

    alert_dict = alert.model_dump()
    alert_dict['created_at'] = alert_dict['created_at'].isoformat()
    await db.alerts.insert_one(alert_dict)

    return {
        'success': True,
        'alert_id': alert.id,
        'message': 'Alert created successfully'
    }




@router.put("/inbox/alerts/{alert_id}/mark-read")
async def mark_alert_read(
    alert_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark alert as read"""
    await db.alerts.update_one(
        {'id': alert_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'read',
            'read_at': datetime.now(UTC).isoformat()
        }}
    )

    return {'success': True, 'message': 'Alert marked as read'}




@router.get("/inbox/summary")
async def get_inbox_summary(
    current_user: User = Depends(get_current_user)
):
    """
    Get inbox summary
    - Counts by type
    - Counts by priority
    - Recent alerts
    """
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'assigned_to': current_user.name},
            {'assigned_to': None}
        ]
    }

    # Count by type
    type_counts = {}
    async for alert in db.alerts.find(match_criteria):
        alert_type = alert.get('alert_type', 'other')
        type_counts[alert_type] = type_counts.get(alert_type, 0) + 1

    # Count by priority
    urgent = await db.alerts.count_documents({**match_criteria, 'priority': 'urgent', 'status': 'unread'})
    high = await db.alerts.count_documents({**match_criteria, 'priority': 'high', 'status': 'unread'})
    normal = await db.alerts.count_documents({**match_criteria, 'priority': 'normal', 'status': 'unread'})

    return {
        'total_unread': urgent + high + normal,
        'by_priority': {
            'urgent': urgent,
            'high': high,
            'normal': normal
        },
        'by_type': type_counts,
        'summary': f"{urgent} urgent, {high} high priority alerts"
    }


# ============= ENHANCED POS MODULE =============



@router.get("/notifications/preferences")
async def get_notification_preferences(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get user notification preferences
    """
    current_user = await get_current_user(credentials)

    preferences = await db.notification_preferences.find_one(
        {'user_id': current_user.id},
        {'_id': 0},
    )

    if not preferences:
        # Return default preferences
        default_prefs = {
            'user_id': current_user.id,
            'preferences': [
                {'type': 'approval_request', 'enabled': True, 'channels': ['in_app']},
                {'type': 'approval_approved', 'enabled': True, 'channels': ['in_app']},
                {'type': 'approval_rejected', 'enabled': True, 'channels': ['in_app']},
                {'type': 'low_stock_alert', 'enabled': True, 'channels': ['in_app']},
                {'type': 'revenue_alert', 'enabled': True, 'channels': ['in_app']},
                {'type': 'overbooking_risk', 'enabled': True, 'channels': ['in_app']},
                {'type': 'maintenance_urgent', 'enabled': True, 'channels': ['in_app']},
                {'type': 'cash_flow_warning', 'enabled': True, 'channels': ['in_app']}
            ]
        }
        return default_prefs

    return preferences


# 2. PUT /api/notifications/preferences - Update notification preferences


@router.put("/notifications/preferences")
async def update_notification_preferences(
    request: NotificationPreferenceRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v92 DW: auth-only
):
    """
    Update notification preferences for a specific notification type
    """
    current_user = await get_current_user(credentials)

    # Update or create preferences
    await db.notification_preferences.update_one(
        {'user_id': current_user.id},
        {
            '$set': {
                f'preferences.{request.notification_type}': {
                    'enabled': request.enabled,
                    'channels': request.channels
                }
            }
        },
        upsert=True
    )

    return {
        'message': 'Bildirim tercihleri güncellendi',
        'notification_type': request.notification_type,
        'enabled': request.enabled,
        'updated_preference': {
            'type': request.notification_type,
            'enabled': request.enabled,
            'channels': request.channels
        }
    }


# 3. GET /api/notifications/list - Get notifications


@router.get("/notifications/list")
async def get_notifications_list(
    unread_only: bool = False,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get notifications for current user
    Filter by unread_only
    """
    current_user = await get_current_user(credentials)

    cache_key = (current_user.id, unread_only, limit)
    now = time.monotonic()
    cached = _NOTIF_LIST_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _NOTIF_LIST_TTL_SEC:
        return cached[1]

    await _ensure_notif_indexes()

    query = {
        '$or': [
            {'user_id': current_user.id},
            {'tenant_id': current_user.tenant_id, 'user_id': None}  # System-wide notifications
        ]
    }

    if unread_only:
        query['read'] = False

    notifications = []
    async for notif in db.notifications.find(query).sort('created_at', -1).limit(limit):
        notifications.append({
            'id': notif['id'],
            'type': notif.get('type', 'general'),
            'title': notif.get('title', ''),
            'message': notif.get('message', ''),
            'priority': notif.get('priority', 'normal'),
            'read': notif.get('read', False),
            'created_at': notif.get('created_at'),
            'action_url': notif.get('action_url')
        })

    result = {
        'notifications': notifications,
        'count': len(notifications),
        'unread_count': len([n for n in notifications if not n['read']])
    }
    _NOTIF_LIST_CACHE[cache_key] = (now, result)
    return result


# 4. PUT /api/notifications/{notification_id}/mark-read - Mark as read


@router.put("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v92 DW: auth-only
):
    """
    Mark a notification as read
    """
    current_user = await get_current_user(credentials)

    result = await db.notifications.update_one(
        {
            'id': notification_id,
            '$or': [
                {'user_id': current_user.id},
                {'tenant_id': current_user.tenant_id}
            ]
        },
        {'$set': {'read': True, 'read_at': datetime.now(UTC).isoformat()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {
        'message': 'Bildirim okundu olarak işaretlendi',
        'notification_id': notification_id
    }


# 5. POST /api/notifications/send-system-alert - Send system alert (internal use)


@router.post("/notifications/send-system-alert")
async def send_system_alert(
    request: SystemAlertRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v89 DW: auth-only
):
    """
    Send system-wide alert to specific roles
    Only admin can send system alerts
    """
    current_user = await get_current_user(credentials)

    from core.security import _is_super_admin
    if not _is_super_admin(current_user) and current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Only admin can send system alerts")

    # Get users with target roles
    query = {'tenant_id': current_user.tenant_id}
    if request.target_roles:
        query['role'] = {'$in': request.target_roles}

    users = await db.users.find(query).to_list(1000)

    # Create notifications for each user
    notifications_created = 0
    for target_user in users:
        notification = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'user_id': target_user['id'],
            'type': request.type,
            'title': request.title,
            'message': request.message,
            'priority': request.priority,
            'read': False,
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.notifications.insert_one(notification)
        notifications_created += 1

    return {
        'message': 'Sistem uyarısı gönderildi',
        'notifications_sent': notifications_created,
        'target_roles': request.target_roles
    }


# ============================================================================
# MULTI-PROPERTY QUICK SWITCH - Çoklu Tesis Hızlı Geçişi
# ============================================================================

# 1. GET /api/properties/quick-list - Get quick property list

