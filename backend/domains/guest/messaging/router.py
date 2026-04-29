"""
Guest / Messaging Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.audit import log_audit_event
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.schemas import SendEmailRequest, SendSMSRequest, SendWhatsAppRequest, User
from modules.pms_core.role_permission_service import require_op  # v100 DW

logger = logging.getLogger(__name__)

def _time_ago(ts: Any) -> str:
    """Return a short relative time string like '5m ago' for a timestamp."""
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except Exception:
        return ""


router = APIRouter(prefix="/api", tags=["Guest / Messaging"])

# Time window (in seconds) during which a sender can still recall their own
# internal message. Outside of this window the message is locked in for audit
# integrity and recall is rejected with HTTP 400.
RECALL_WINDOW_SECONDS = 5 * 60  # 5 minutes

# Same 5-minute window applies to in-place edits. After the window the message
# is treated as historical record and can no longer be modified — operators
# who want to clarify must send a follow-up message instead. The window is
# intentionally identical to RECALL_WINDOW_SECONDS so the menu logic stays
# simple ("if you can recall it, you can also edit it").
EDIT_WINDOW_SECONDS = 5 * 60  # 5 minutes


# Single source of truth for "which department a user belongs to". The
# canonical `User` model does not carry a `department` field — the value
# is derived from `role`. Both the send path (Task #?) and the history
# visibility check (Task #39) need this mapping, so it lives here as a
# reusable helper instead of being duplicated inline.
_ROLE_DEPARTMENT_MAPPING: dict[str, str] = {
    'front_desk': 'Reception',
    'housekeeping': 'Housekeeping',
    'maintenance': 'Maintenance',
    'finance': 'Finance',
    'supervisor': 'Management',
    'admin': 'Management',
}


def _department_for_user(user) -> str:
    """Return the department label used to address internal messages.

    Falls back to an explicit `user.department` attribute if the deployment
    has been customised to set one (some tenants store a per-user override
    on the user document); otherwise derives it from the role mapping the
    send-message endpoint uses.
    """
    explicit = getattr(user, 'department', None)
    if explicit:
        return explicit
    role = getattr(user, 'role', None)
    role_value = getattr(role, 'value', role) if role is not None else None
    if role_value is None:
        return 'General'
    return _ROLE_DEPARTMENT_MAPPING.get(str(role_value), 'General')


# ── Inline Models ──

class MessageType(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"


class AutoMessageTrigger(str, Enum):
    PRE_ARRIVAL = "pre_arrival"
    CHECK_IN_REMINDER = "check_in_reminder"
    POST_CHECKOUT = "post_checkout"
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"


class SendMessageRequest(BaseModel):
    guest_id: str
    message_type: MessageType
    recipient: str
    message_content: str
    booking_id: str | None = None

    @field_validator('message_type', mode='before')
    @classmethod
    def lowercase_message_type(cls, v):
        """Convert message type to lowercase for case-insensitive validation"""
        if isinstance(v, str):
            return v.lower()
        return v


class SentMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: str | None = None
    message_type: MessageType
    recipient: str  # phone or email
    message_content: str
    status: str = "sent"  # sent, delivered, failed
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    template_name: str
    message_type: MessageType
    trigger: AutoMessageTrigger
    message_content: str
    active: bool = True
    variables: list[str] = []  # e.g., ['{guest_name}', '{room_number}', '{check_in_date}']


class InternalMessage(BaseModel):
    """Internal messaging between departments"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    from_user_name: str
    from_department: str
    to_user_id: str | None = None  # None = broadcast to department
    to_user_name: str | None = None
    to_department: str | None = None  # None = all departments
    message: str
    priority: str = "normal"  # low, normal, high, urgent
    message_type: str = "text"  # text, task, alert, announcement
    attachments: list[str] = []
    read: bool = False
    read_at: datetime | None = None
    replied_to: str | None = None  # Original message ID if this is a reply
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Edit metadata — populated by PATCH /messaging/internal/{id}. The
    # `edit_history` array preserves every previous version (oldest first) so
    # operators can later prove what was originally said.
    edited: bool = False
    edited_at: datetime | None = None
    edit_history: list[dict] = []


@router.post("/whatsapp/send-confirmation")
async def send_whatsapp_confirmation(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """WhatsApp ile rezervasyon onayı gönder"""
    from domains.guest.whatsapp_service import whatsapp_service

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    # Get guest
    guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})

    if not guest or not guest.get('phone'):
        raise HTTPException(status_code=400, detail="Misafir telefon numarası bulunamadı")

    # Get room
    room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})

    booking_details = {
        'booking_id': booking['id'],
        'guest_name': guest['name'],
        'check_in': booking['check_in'][:10] if isinstance(booking['check_in'], str) else str(booking['check_in'])[:10],
        'check_out': booking['check_out'][:10] if isinstance(booking['check_out'], str) else str(booking['check_out'])[:10],
        'room_type': room.get('room_type', 'Standard') if room else 'Standard',
        'total_amount': booking['total_amount']
    }

    await whatsapp_service.send_booking_confirmation(guest['phone'], booking_details)

    return {
        'success': True,
        'message': 'WhatsApp onay mesajı gönderildi',
        'phone': guest['phone']
    }


@router.post("/messaging/send-whatsapp")
async def send_whatsapp_message(
    request: SendWhatsAppRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send WhatsApp message to guest"""
    msg_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'channel': 'whatsapp',
        'to': request.to,
        'message': request.message,
        'booking_id': request.booking_id,
        'status': 'sent',
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id
    }

    msg_copy = msg_record.copy()
    await db.messages.insert_one(msg_copy)
    return {'message': 'WhatsApp message sent successfully', 'message_id': msg_record['id']}



@router.post("/messaging/send-email")
async def send_email_message(
    request: SendEmailRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send email to guest"""
    msg_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'channel': 'email',
        'to': request.to,
        'subject': request.subject,
        'message': request.message,
        'booking_id': request.booking_id,
        'status': 'sent',
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id
    }

    msg_copy = msg_record.copy()
    await db.messages.insert_one(msg_copy)
    return {'message': 'Email sent successfully', 'message_id': msg_record['id']}



@router.post("/messaging/send-sms")
async def send_sms_message(
    request: SendSMSRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send SMS to guest"""
    msg_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'channel': 'sms',
        'to': request.to,
        'message': request.message,
        'booking_id': request.booking_id,
        'status': 'sent',
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id
    }

    msg_copy = msg_record.copy()
    await db.messages.insert_one(msg_copy)
    return {'message': 'SMS sent successfully', 'message_id': msg_record['id']}



@router.get("/messaging/conversations")
async def get_conversations(
    channel: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get all message conversations"""
    query = {'tenant_id': current_user.tenant_id}
    if channel:
        query['channel'] = channel

    messages = await db.messages.find(
        query,
        {'_id': 0}
    ).sort('sent_at', -1).limit(100).to_list(100)

    return {'messages': messages, 'count': len(messages)}



@router.get("/messaging/ota-integrations")
async def get_ota_integrations(current_user: User = Depends(get_current_user)):
    """Get OTA messaging integrations"""
    integrations = await db.ota_integrations.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)

    return {'integrations': integrations, 'count': len(integrations)}


# ========================================
# 2. Full RMS - Revenue Management System
# ============= FULL RMS — MOVED to domains/revenue/rms_router.py =============

# ========================================
# 3. Mobile Housekeeping App
# ========================================



@router.post("/messaging/internal/send")
async def send_internal_message(
    message: str,
    to_department: str | None = None,
    to_user_id: str | None = None,
    priority: str = "normal",
    message_type: str = "text",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """
    Send internal message
    - Department to department (e.g., Reception → HK)
    - Department to specific user (e.g., HK → Maintenance tech)
    - Broadcast to all (e.g., GM → All departments)

    Multi-tenant: when targeting a specific user, the recipient must belong to
    the sender's tenant. Cross-tenant addressing is rejected with 404.

    Urgent priority is gated by a separate permission (`send_urgent_message`)
    because it triggers a system alert on the recipient. Default messaging
    access alone is NOT enough — only roles explicitly granted that permission
    (supervisor, admin, super_admin) can use it.
    """
    # Gate the "urgent" channel behind a dedicated permission so that the
    # alarm-triggering path is reserved for designated responders only.
    if priority == 'urgent':
        from core.security import _is_super_admin
        from modules.pms_core.role_permission_service import RolePermissionService
        if not _is_super_admin(current_user) and not RolePermissionService().check_permission(
            current_user.role, 'send_urgent_message'
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    'Acil mesaj gönderme yetkiniz yok. Bu kanal yalnızca '
                    'yetkili rollere (yönetici/süpervizör) açıktır.'
                ),
            )

    # Get to_user info if specified — MUST be scoped to sender's tenant
    to_user_name = None
    if to_user_id:
        to_user = await db.users.find_one({
            'id': to_user_id,
            'tenant_id': current_user.tenant_id,
        })
        if not to_user:
            raise HTTPException(status_code=404, detail="Alıcı kullanıcı bulunamadı")
        to_user_name = to_user.get('name')

    # Determine from_department based on user role
    from_department = _department_for_user(current_user)

    message_obj = InternalMessage(
        tenant_id=current_user.tenant_id,
        from_user_id=current_user.id,
        from_user_name=current_user.name,
        from_department=from_department,
        to_user_id=to_user_id,
        to_user_name=to_user_name,
        to_department=to_department,
        message=message,
        priority=priority,
        message_type=message_type
    )

    msg_dict = message_obj.model_dump()
    msg_dict['created_at'] = msg_dict['created_at'].isoformat()
    await db.internal_messages.insert_one(msg_dict)

    # Create alert + audit trail for urgent messages
    if priority == 'urgent':
        await db.alerts.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'alert_type': 'internal_message',
            'priority': 'urgent',
            'title': f'Urgent message from {from_department}',
            'description': message[:100],
            'source_module': 'messaging',
            'source_id': message_obj.id,
            'assigned_to': to_user_name,
            'status': 'unread',
            'created_at': datetime.now(UTC).isoformat()
        })

        # Audit trail: every urgent internal message is logged separately
        # so abuse / unnecessary alarms can be reviewed by managers later.
        recipient_label = (
            to_user_name
            or to_department
            or 'all_departments'
        )
        await log_audit_event(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="send_urgent_internal_message",
            entity_type="internal_message",
            entity_id=message_obj.id,
            details=(
                f"Acil mesaj: {current_user.name} ({from_department}) → "
                f"{recipient_label} | {message[:120]}"
            ),
            before_value=None,
            # Task #27: acil mesaj kayıtları audit timeline'da severity
            # filtresi ile öne çıksın diye "warning" olarak işaretlenir.
            severity="warning",
            after_value={
                "message_id": message_obj.id,
                "from_user_id": current_user.id,
                "from_user_name": current_user.name,
                "from_department": from_department,
                "to_user_id": to_user_id,
                "to_user_name": to_user_name,
                "to_department": to_department,
                "priority": "urgent",
                "message_type": message_type,
                "message_preview": message[:240],
                "sent_at": msg_dict['created_at'],
            },
            db=db,
        )

    # ── Real-time delivery: WebSocket push to recipients ──
    # `delivered_to` is what the inbox endpoint returns to clients, so we
    # mirror its shape here so the frontend can drop it straight into state
    # without round-tripping through the inbox endpoint.
    realtime_payload = {
        'id': message_obj.id,
        'from_user_id': message_obj.from_user_id,
        'from_user_name': message_obj.from_user_name,
        'from_department': message_obj.from_department,
        'to_user_id': message_obj.to_user_id,
        'to_user_name': message_obj.to_user_name,
        'to_department': message_obj.to_department or 'All',
        'message': message_obj.message,
        'priority': message_obj.priority,
        'message_type': message_obj.message_type,
        'read': False,
        'created_at': msg_dict['created_at'],
        'time_ago': '0s ago',
    }
    try:
        from websocket_server import broadcast_internal_message
        await broadcast_internal_message(
            current_user.tenant_id,
            realtime_payload,
            to_user_id=to_user_id,
            to_department=to_department,
        )
    except Exception as ws_err:
        logger.warning("internal_message live push failed: %s", ws_err)

    # Web Push (PWA / OS-level) for urgent messages — delivered even when
    # the recipient has no tab open. Best-effort: silent failure if VAPID
    # is not configured or pywebpush is missing.
    if priority == 'urgent':
        try:
            from domains.guest.messaging.web_push import dispatch_internal_message_push
            push_result = await dispatch_internal_message_push(
                tenant_id=current_user.tenant_id,
                payload={
                    'title': f'Acil mesaj — {message_obj.from_user_name}',
                    'body': message[:140],
                    'tag': f'internal-msg-{message_obj.id}',
                    'data': {
                        'kind': 'internal_message',
                        'message_id': message_obj.id,
                        'priority': 'urgent',
                        'url': '/app/dashboard?tab=communication',
                    },
                },
                to_user_id=to_user_id,
                to_department=to_department,
            )
            # Task #32: günlük rollup'a yaz (best-effort).
            try:
                from core.database import db as _metrics_db
                from domains.guest.messaging.web_push_metrics import record_dispatch
                await record_dispatch(
                    _metrics_db,
                    tenant_id=current_user.tenant_id,
                    attempted=int(push_result.get('attempted', 0) or 0),
                    sent=int(push_result.get('sent', 0) or 0),
                    failed=int(push_result.get('failed', 0) or 0),
                    pruned=int(push_result.get('pruned', 0) or 0),
                )
            except Exception as metric_err:
                logger.warning("urgent web-push metric record failed: %s", metric_err)
        except Exception as push_err:
            logger.warning("urgent web-push dispatch failed: %s", push_err)

    return {
        'success': True,
        'message_id': message_obj.id,
        'delivered_to': to_user_name or to_department or 'All departments'
    }




# ── Presence (task #25): "who is online right now in my tenant?" ──

@router.get("/messaging/internal/presence/online")
async def get_internal_presence_online(
    current_user: User = Depends(get_current_user),
):
    """Return user_ids currently connected via WebSocket in the caller's
    tenant. Used by the compose dialog's "Sadece çevrimiçi" filter so
    operators can quickly see which colleagues will receive a DM in real
    time vs. land in their inbox for later.

    Always tenant-scoped — never leaks presence across tenants. The
    current user's own id is intentionally INCLUDED so the frontend
    does not have to special-case it (the picker already filters self
    out before rendering).
    """
    try:
        from websocket_server import get_online_user_ids
        user_ids = get_online_user_ids(current_user.tenant_id)
    except Exception as e:
        # Presence is a UX hint, not a security boundary. If the
        # in-memory map can't be read for some reason, return an empty
        # list rather than 500 — the picker degrades gracefully (the
        # toggle just shows "Eşleşen kullanıcı yok").
        logger.warning(f"presence read failed for tenant {current_user.tenant_id}: {e}")
        user_ids = []
    return {"user_ids": user_ids, "count": len(user_ids)}


# ── Web Push (PWA) subscription endpoints for the internal chat ──

@router.get("/messaging/internal/push/vapid-public-key")
async def get_internal_chat_vapid_key(current_user: User = Depends(get_current_user)):
    """Return the active VAPID public key so the browser can subscribe."""
    from domains.guest.messaging.web_push import get_vapid_keys
    keys = await get_vapid_keys()
    return {'public_key': keys['public_key']}


class _PushSubscribeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    endpoint: str
    keys: dict[str, str]
    user_agent: str | None = None


@router.post("/messaging/internal/push/subscribe")
async def subscribe_internal_chat_push(
    body: _PushSubscribeBody,
    current_user: User = Depends(get_current_user),
):
    """Persist a browser PushSubscription so urgent internal messages can be
    delivered as OS-level notifications even when no tab is open."""
    from domains.guest.messaging.web_push import store_subscription

    department_mapping = {
        'front_desk': 'Reception',
        'housekeeping': 'Housekeeping',
        'maintenance': 'Maintenance',
        'finance': 'Finance',
        'supervisor': 'Management',
        'admin': 'Management',
        'super_admin': 'Management',
        'owner': 'Management',
        'sales': 'Reception',
    }
    role_value = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    department = department_mapping.get(role_value, 'General')

    try:
        await store_subscription(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            department=department,
            subscription={'endpoint': body.endpoint, 'keys': body.keys},
            user_agent=body.user_agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'success': True, 'department': department}


@router.delete("/messaging/internal/push/subscribe")
async def unsubscribe_internal_chat_push(
    endpoint: str,
    current_user: User = Depends(get_current_user),
):
    from domains.guest.messaging.web_push import remove_subscription
    deleted = await remove_subscription(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        endpoint=endpoint,
    )
    return {'success': True, 'deleted': deleted}


@router.get("/messaging/internal/inbox")
async def get_internal_messages_inbox(
    department: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """
    Get internal messages inbox
    - Messages sent to me
    - Messages sent to my department
    - Broadcast messages
    """
    # Determine user's department
    department_mapping = {
        'front_desk': 'Reception',
        'housekeeping': 'Housekeeping',
        'maintenance': 'Maintenance',
        'finance': 'Finance',
        'supervisor': 'Management',
        'admin': 'Management'
    }
    my_department = department_mapping.get(current_user.role.value, 'General')

    match_criteria = {
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'to_user_id': current_user.id},  # Direct to me
            {'to_department': my_department},  # To my department
            {'to_department': None}  # Broadcast
        ]
    }

    # Per-user read tracking: a message is "read by me" if my user_id is in read_by[].
    # Legacy DM messages may still use the global `read` field — those are treated as
    # read by the recipient when read=True.
    if unread_only:
        match_criteria['read_by'] = {'$ne': current_user.id}

    if department:
        match_criteria['from_department'] = department

    messages = []
    async for msg in db.internal_messages.find(match_criteria).sort('created_at', -1).limit(limit):
        read_by = msg.get('read_by') or []
        # Per-user read flag (works for DM, department, and broadcast messages alike)
        is_read = current_user.id in read_by
        # Legacy fallback: old DMs only set the global `read` flag for the lone recipient
        if not is_read and msg.get('to_user_id') == current_user.id and msg.get('read'):
            is_read = True

        is_deleted = bool(msg.get('deleted'))
        messages.append({
            'id': msg.get('id'),
            'from_user_id': msg.get('from_user_id'),
            'from_user_name': msg.get('from_user_name'),
            'from_department': msg.get('from_department'),
            'to_user_id': msg.get('to_user_id'),
            'to_user_name': msg.get('to_user_name'),
            'to_department': msg.get('to_department') or 'All',
            # Mask content for recalled messages — neither sender nor recipient
            # should see the original wording after a recall.
            'message': '' if is_deleted else msg.get('message'),
            'priority': msg.get('priority'),
            'message_type': msg.get('message_type'),
            'read': is_read,
            'deleted': is_deleted,
            'deleted_at': msg.get('deleted_at'),
            # Edit metadata — surfaced so the UI can render a "düzenlendi"
            # badge on edited messages on both the sender and recipient side.
            # Recalled messages drop the badge to avoid mixed signals.
            'edited': bool(msg.get('edited')) and not is_deleted,
            'edited_at': msg.get('edited_at'),
            'created_at': msg.get('created_at'),
            'time_ago': _time_ago(msg.get('created_at'))
        })

    unread_count = await db.internal_messages.count_documents({
        **match_criteria,
        'read_by': {'$ne': current_user.id},
    })

    return {
        'messages': messages,
        'total_count': len(messages),
        'unread_count': unread_count,
        'my_department': my_department
    }




@router.put("/messaging/internal/{message_id}/mark-read")
async def mark_internal_message_read(
    message_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark internal message as read for the current user only.

    Authorization: caller must be a legitimate recipient of the message —
    direct addressee, member of the targeted department, or recipient of a
    broadcast. Otherwise returns 404 (no information disclosure about
    existence of messages outside the caller's scope).
    """
    department_mapping = {
        'front_desk': 'Reception',
        'housekeeping': 'Housekeeping',
        'maintenance': 'Maintenance',
        'finance': 'Finance',
        'supervisor': 'Management',
        'admin': 'Management',
    }
    my_department = department_mapping.get(current_user.role.value, 'General')

    result = await db.internal_messages.update_one(
        {
            'id': message_id,
            'tenant_id': current_user.tenant_id,
            '$or': [
                {'to_user_id': current_user.id},  # direct DM to me
                {'to_department': my_department},  # to my department
                {'to_department': None},  # broadcast
            ],
        },
        {
            '$addToSet': {'read_by': current_user.id},
            '$set': {'last_read_at': datetime.now(UTC).isoformat()},
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı veya yetkiniz yok")

    # Live read receipt: notify the sender's open thread without waiting
    # for the next 15-sec poll. Best-effort — polling fallback covers the
    # case where WS is unavailable.
    if result.modified_count > 0:
        try:
            msg_doc = await db.internal_messages.find_one(
                {'id': message_id, 'tenant_id': current_user.tenant_id},
                {'_id': 0, 'from_user_id': 1},
            )
            sender_id = (msg_doc or {}).get('from_user_id')
            if sender_id and sender_id != current_user.id:
                from websocket_server import broadcast_internal_message_read
                await broadcast_internal_message_read(
                    reader_id=current_user.id,
                    sender_id=sender_id,
                    tenant_id=current_user.tenant_id,
                    message_ids=[message_id],
                    partner_id=current_user.id,
                )
        except Exception as _e:  # pragma: no cover - non-fatal
            logger.debug(f"WS read-receipt emit skipped: {_e}")

    return {'success': True, 'message': 'Message marked as read'}




@router.post("/messaging/internal/mark-all-read")
async def mark_all_internal_messages_read(
    current_user: User = Depends(get_current_user),
):
    """Mark every internal message addressed to the current user as read.

    Scoped to the caller's tenant AND the messages they are a legitimate
    recipient of — direct DMs to me, messages to my department, or
    broadcasts. Idempotent: running it twice in a row is a no-op the
    second time. Returns the number of newly-marked messages so the UI
    can confirm the operation succeeded.
    """
    department_mapping = {
        'front_desk': 'Reception',
        'housekeeping': 'Housekeeping',
        'maintenance': 'Maintenance',
        'finance': 'Finance',
        'supervisor': 'Management',
        'admin': 'Management',
    }
    role_value = (
        current_user.role.value
        if hasattr(current_user.role, 'value')
        else current_user.role
    )
    my_department = department_mapping.get(role_value, 'General')

    now_iso = datetime.now(UTC).isoformat()
    result = await db.internal_messages.update_many(
        {
            'tenant_id': current_user.tenant_id,
            'read_by': {'$ne': current_user.id},
            '$or': [
                {'to_user_id': current_user.id},  # direct DM to me
                {'to_department': my_department},  # to my department
                {'to_department': None},  # broadcast
            ],
        },
        {
            '$addToSet': {'read_by': current_user.id},
            '$set': {'last_read_at': now_iso},
        },
    )

    return {
        'success': True,
        'updated_count': result.modified_count,
    }


@router.get("/messaging/internal/conversations")
async def list_dm_conversations(
    current_user: User = Depends(get_current_user),
):
    """
    List DM conversation partners for the current user.

    Aggregates all internal messages where either the sender or recipient is
    the current user AND the message is a direct DM (i.e. `to_user_id` is set,
    excluding department or broadcast messages). Returns one row per partner
    with the most recent message preview, timestamp, and unread count.
    """
    pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'to_user_id': {'$ne': None},
                '$or': [
                    {'from_user_id': current_user.id},
                    {'to_user_id': current_user.id},
                ],
            }
        },
        {
            '$addFields': {
                'partner_id': {
                    '$cond': [
                        {'$eq': ['$from_user_id', current_user.id]},
                        '$to_user_id',
                        '$from_user_id',
                    ]
                },
                'partner_name': {
                    '$cond': [
                        {'$eq': ['$from_user_id', current_user.id]},
                        '$to_user_name',
                        '$from_user_name',
                    ]
                },
                '_from_me': {'$eq': ['$from_user_id', current_user.id]},
                '_is_unread_for_me': {
                    '$and': [
                        {'$eq': ['$to_user_id', current_user.id]},
                        {
                            '$not': {
                                '$in': [
                                    current_user.id,
                                    {'$ifNull': ['$read_by', []]},
                                ]
                            }
                        },
                        {'$ne': ['$read', True]},
                    ]
                },
            }
        },
        {'$match': {'partner_id': {'$ne': None}}},
        {'$sort': {'created_at': -1}},
        {
            '$group': {
                '_id': '$partner_id',
                'partner_name': {'$first': '$partner_name'},
                'last_message': {'$first': '$message'},
                'last_message_at': {'$first': '$created_at'},
                'last_from_me': {'$first': '$_from_me'},
                'last_priority': {'$first': '$priority'},
                # Track whether the most recent message was recalled so we can
                # show the right preview text in the conversations list.
                'last_deleted': {'$first': {'$ifNull': ['$deleted', False]}},
                'unread_count': {
                    '$sum': {'$cond': ['$_is_unread_for_me', 1, 0]}
                },
            }
        },
        {'$sort': {'last_message_at': -1}},
        {'$limit': 200},
    ]

    rows: list[dict] = []
    partner_ids: list[str] = []
    async for doc in db.internal_messages.aggregate(pipeline):
        partner_id = doc.get('_id')
        if not partner_id:
            continue
        partner_ids.append(partner_id)
        last_deleted = bool(doc.get('last_deleted'))
        rows.append({
            'user_id': partner_id,
            'user_name': doc.get('partner_name') or 'Bilinmeyen',
            # Show a tombstone preview when the most recent message was recalled.
            'last_message': 'Bu mesaj kaldırıldı' if last_deleted else (doc.get('last_message') or ''),
            'last_message_at': doc.get('last_message_at'),
            'last_from_me': bool(doc.get('last_from_me')),
            'last_priority': doc.get('last_priority') or 'normal',
            'last_deleted': last_deleted,
            'unread_count': int(doc.get('unread_count') or 0),
            'time_ago': _time_ago(doc.get('last_message_at')),
        })

    # Resolve partner display names from the users collection — covers cases
    # where historical messages stored an empty/stale `to_user_name`/`from_user_name`.
    if partner_ids:
        names_by_id: dict[str, str] = {}
        roles_by_id: dict[str, str] = {}
        async for u in db.users.find(
            {'id': {'$in': partner_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'name': 1, 'username': 1, 'email': 1, 'role': 1, 'is_active': 1},
        ):
            names_by_id[u['id']] = u.get('name') or u.get('username') or u.get('email') or 'Kullanıcı'
            roles_by_id[u['id']] = u.get('role') or ''
        for row in rows:
            resolved = names_by_id.get(row['user_id'])
            if resolved:
                row['user_name'] = resolved
            row['user_role'] = roles_by_id.get(row['user_id'], '')

    return {
        'conversations': rows,
        'total_count': len(rows),
    }


@router.get("/messaging/internal/conversation/{user_id}")
async def get_conversation_thread(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get conversation thread with specific user"""
    messages = []
    async for msg in db.internal_messages.find({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'from_user_id': current_user.id, 'to_user_id': user_id},
            {'from_user_id': user_id, 'to_user_id': current_user.id}
        ]
    }).sort('created_at', 1):
        read_by = msg.get('read_by') or []
        is_from_me = msg.get('from_user_id') == current_user.id
        # For my own outgoing messages, "read" means the recipient has read it.
        # For incoming messages, "read" means I have read it.
        if is_from_me:
            is_read = user_id in read_by or bool(msg.get('read'))
        else:
            is_read = current_user.id in read_by or bool(msg.get('read'))
        is_deleted = bool(msg.get('deleted'))
        messages.append({
            'id': msg.get('id'),
            'from_user_id': msg.get('from_user_id'),
            'from_user_name': msg.get('from_user_name'),
            'to_user_id': msg.get('to_user_id'),
            'to_user_name': msg.get('to_user_name'),
            # Recalled messages are masked — the original text is no longer
            # surfaced to either party (they only see the tombstone).
            'message': '' if is_deleted else msg.get('message'),
            'priority': msg.get('priority'),
            'created_at': msg.get('created_at'),
            'time_ago': _time_ago(msg.get('created_at')),
            'is_from_me': is_from_me,
            'read': is_read,
            'deleted': is_deleted,
            'deleted_at': msg.get('deleted_at'),
            # Edit metadata — both sides see the "düzenlendi" badge after a
            # PATCH lands. Suppressed for recalled messages so the tombstone
            # stays the only signal.
            'edited': bool(msg.get('edited')) and not is_deleted,
            'edited_at': msg.get('edited_at'),
        })

    return {
        'user_id': user_id,
        'message_count': len(messages),
        'messages': messages
    }


@router.put("/messaging/internal/conversation/{user_id}/mark-read")
async def mark_conversation_read(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Mark every DM in the thread with `user_id` (sent by them, addressed to me)
    as read by the current user.

    Idempotent — only updates messages where the current user's id is not
    already in `read_by`. Returns the number of newly-marked messages.
    """
    now_iso = datetime.now(UTC).isoformat()
    # Capture the IDs about to be marked so we can include them in the
    # live read-receipt event. Doing this before the update keeps the
    # event payload accurate (after update they would no longer match
    # the `read_by:{$ne:...}` filter).
    pending_ids: list[str] = []
    if user_id != current_user.id:
        async for doc in db.internal_messages.find(
            {
                'tenant_id': current_user.tenant_id,
                'from_user_id': user_id,
                'to_user_id': current_user.id,
                'read_by': {'$ne': current_user.id},
            },
            {'_id': 0, 'id': 1},
        ):
            mid = doc.get('id')
            if mid:
                pending_ids.append(mid)

    result = await db.internal_messages.update_many(
        {
            'tenant_id': current_user.tenant_id,
            'from_user_id': user_id,
            'to_user_id': current_user.id,
            'read_by': {'$ne': current_user.id},
        },
        {
            '$addToSet': {'read_by': current_user.id},
            '$set': {'last_read_at': now_iso, 'read': True},
        },
    )

    # Live read receipt for the sender's open thread. Best-effort.
    if result.modified_count > 0 and user_id and user_id != current_user.id:
        try:
            from websocket_server import broadcast_internal_message_read
            await broadcast_internal_message_read(
                reader_id=current_user.id,
                sender_id=user_id,
                tenant_id=current_user.tenant_id,
                message_ids=pending_ids,
                partner_id=current_user.id,
            )
        except Exception as _e:  # pragma: no cover - non-fatal
            logger.debug(f"WS read-receipt emit skipped: {_e}")

    return {
        'success': True,
        'updated_count': result.modified_count,
    }


class _EditInternalMessageBody(BaseModel):
    """Body for PATCH /messaging/internal/{message_id}.

    `message` is the new full text. We require the full body (rather than a
    diff) so the server-side validation surface stays trivial and the edit
    history snapshot is unambiguous.
    """
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=1, max_length=2000)

    @field_validator('message', mode='before')
    @classmethod
    def _strip_message(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


@router.patch("/messaging/internal/{message_id}")
async def edit_internal_message(
    message_id: str,
    body: _EditInternalMessageBody,
    current_user: User = Depends(get_current_user),
):
    """Edit the text of an internal message previously sent by the current user.

    - Only the original sender may edit their own message.
    - Editing is allowed within EDIT_WINDOW_SECONDS (5 minutes) of the original
      send time. After the window the message is locked in for audit integrity
      and the request is rejected with HTTP 400.
    - A recalled (deleted) message can no longer be edited — once the
      tombstone is up we don't reanimate it.
    - Every edit appends the previous text + timestamp + actor to
      `edit_history`, so the original wording is never lost. The current
      `message` field is replaced with the new text and `edited`/`edited_at`
      flags are set so both sender and recipient see the "düzenlendi" badge.
    - When a recipient is online, the change is broadcast over the existing
      internal-chat WebSocket so their thread updates without waiting for
      the safety-net poll.
    """
    new_text = body.message
    if not new_text:
        raise HTTPException(status_code=400, detail="Mesaj metni boş olamaz")

    msg = await db.internal_messages.find_one({
        'id': message_id,
        'tenant_id': current_user.tenant_id,
    })
    if not msg:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    if msg.get('from_user_id') != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Sadece kendi gönderdiğiniz mesajları düzenleyebilirsiniz",
        )
    if msg.get('deleted'):
        raise HTTPException(
            status_code=400,
            detail="Geri alınmış mesaj düzenlenemez",
        )

    # No-op short-circuit: if the new text is identical to the current one,
    # don't bump `edited_at` or pollute the history.
    current_text = msg.get('message') or ''
    if new_text == current_text:
        return {
            'success': True,
            'message_id': message_id,
            'edited': bool(msg.get('edited')),
            'edited_at': msg.get('edited_at'),
            'noop': True,
        }

    # Time-window check — mirror of the recall flow.
    created_at_raw = msg.get('created_at')
    created_dt = None
    try:
        if isinstance(created_at_raw, str):
            created_dt = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00'))
        elif isinstance(created_at_raw, datetime):
            created_dt = created_at_raw
        if created_dt is not None and created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=UTC)
    except Exception:
        created_dt = None

    if created_dt is not None:
        elapsed = (datetime.now(UTC) - created_dt).total_seconds()
        if elapsed > EDIT_WINDOW_SECONDS:
            minutes = EDIT_WINDOW_SECONDS // 60
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Bu mesaj {minutes} dakikadan eski olduğu için düzenlenemez."
                ),
            )

    now_iso = datetime.now(UTC).isoformat()
    history_entry = {
        # Snapshot of the *previous* message version so the audit trail can
        # reconstruct the conversation as the recipient originally saw it.
        'message': current_text,
        'edited_at': now_iso,
        'edited_by': current_user.id,
        'edited_by_name': current_user.name,
    }
    await db.internal_messages.update_one(
        {'id': message_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'message': new_text,
                'edited': True,
                'edited_at': now_iso,
                'last_edited_by': current_user.id,
            },
            '$push': {'edit_history': history_entry},
        },
    )

    # Live update: push the new text to the recipient(s) so their open thread
    # reflects the edit immediately. Routing mirrors the original send.
    update_payload = {
        'id': message_id,
        'from_user_id': msg.get('from_user_id'),
        'from_user_name': msg.get('from_user_name'),
        'from_department': msg.get('from_department'),
        'to_user_id': msg.get('to_user_id'),
        'to_user_name': msg.get('to_user_name'),
        'to_department': msg.get('to_department') or 'All',
        'message': new_text,
        'priority': msg.get('priority'),
        'message_type': msg.get('message_type'),
        'edited': True,
        'edited_at': now_iso,
        'created_at': msg.get('created_at'),
        'time_ago': _time_ago(msg.get('created_at')),
    }
    try:
        from websocket_server import broadcast_internal_message_update
        await broadcast_internal_message_update(
            current_user.tenant_id,
            update_payload,
            to_user_id=msg.get('to_user_id'),
            to_department=msg.get('to_department'),
        )
    except Exception as ws_err:
        logger.warning("internal_message edit live push failed: %s", ws_err)

    # Task #40: every successful edit gets its own row in `audit_logs` so the
    # change is visible alongside `recall_internal_message` events in the
    # operator audit/report screens. The `edit_history` array on the message
    # itself is the live source for the "düzenlendi" popover (Task #39); the
    # audit row is the immutable cross-conversation record for compliance and
    # dispute resolution. Failure to write the audit row must NOT break the
    # edit response — the message itself is already mutated.
    try:
        recipient_label = (
            msg.get('to_user_name')
            or msg.get('to_user_id')
            or msg.get('to_department')
            or 'all_departments'
        )
        prev_preview = (current_text or '')[:200]
        new_preview = (new_text or '')[:200]
        # `edit_history` already had `len(...)+1` entries appended above;
        # re-read the count off the in-memory message + the entry we just
        # built so we don't pay an extra DB round-trip.
        prior_history = msg.get('edit_history') or []
        edit_count = len(prior_history) + 1
        await log_audit_event(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="edit_internal_message",
            entity_type="internal_message",
            entity_id=message_id,
            details=(
                f"Mesaj düzenlendi: {current_user.name} → {recipient_label} | "
                f"önceki={prev_preview!r} → yeni={new_preview!r}"
            ),
            before_value={
                "message_id": message_id,
                "from_user_id": msg.get('from_user_id'),
                "from_user_name": msg.get('from_user_name'),
                "from_department": msg.get('from_department'),
                "to_user_id": msg.get('to_user_id'),
                "to_user_name": msg.get('to_user_name'),
                "to_department": msg.get('to_department'),
                "priority": msg.get('priority'),
                "message_type": msg.get('message_type'),
                "created_at": msg.get('created_at'),
                "message_preview": prev_preview,
                "message_length": len(current_text or ''),
            },
            after_value={
                "edited": True,
                "edited_at": now_iso,
                "edited_by": current_user.id,
                "edited_by_name": current_user.name,
                "message_preview_new": new_preview,
                "message_length_new": len(new_text or ''),
                "edit_count": edit_count,
            },
            db=db,
        )
    except Exception:
        logger.exception(
            "Failed to write edit audit entry for message %s", message_id
        )

    return {
        'success': True,
        'message_id': message_id,
        'edited': True,
        'edited_at': now_iso,
        'message': new_text,
    }


@router.get("/messaging/internal/{message_id}/history")
async def get_internal_message_history(
    message_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return the chronological edit history for an internal message
    (Task #39).

    The current `message` field plus the `edit_history` array together
    describe the full lifeline of the message text — the array stores
    every previous version (oldest entry first) and the current text is
    the latest version. The UI uses this to render a "düzenlendi"
    popover so an operator can see exactly what was originally written.

    Authorization mirrors the conversation visibility used elsewhere in
    this router: only the sender, the explicit recipient, or — if the
    message was sent to a department — a member of that department may
    view the history. We deliberately do not expose the history to
    unrelated users in the same tenant.
    """
    msg = await db.internal_messages.find_one({
        'id': message_id,
        'tenant_id': current_user.tenant_id,
    })
    if not msg:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")

    # Visibility check: sender, explicit recipient, or department member.
    # The user's department is derived from their role (not stored on the
    # User model) — we use the same `_department_for_user` helper that the
    # send path uses so authorization stays consistent across the router.
    is_sender = msg.get('from_user_id') == current_user.id
    is_recipient = msg.get('to_user_id') == current_user.id
    user_dept = _department_for_user(current_user)
    is_dept_recipient = (
        bool(msg.get('to_department'))
        and msg.get('to_department') == user_dept
    )
    if not (is_sender or is_recipient or is_dept_recipient):
        raise HTTPException(
            status_code=403,
            detail="Bu mesajın geçmişini görme yetkiniz yok",
        )

    history_raw = msg.get('edit_history') or []
    # Defensive copy + projection — we never want to leak internal Mongo
    # ids or unrelated keys into the API surface.
    versions: list[dict] = []
    for entry in history_raw:
        if not isinstance(entry, dict):
            continue
        versions.append({
            'message': entry.get('message') or '',
            'edited_at': entry.get('edited_at'),
            'edited_by': entry.get('edited_by'),
            'edited_by_name': entry.get('edited_by_name'),
        })

    return {
        'success': True,
        'message_id': message_id,
        'created_at': msg.get('created_at'),
        'edited': bool(msg.get('edited')),
        'edited_at': msg.get('edited_at'),
        'current_message': msg.get('message') or '',
        # Oldest first; the most-recent entry in the list is the version
        # that was *replaced* by the current `message`.
        'history': versions,
    }


@router.delete("/messaging/internal/{message_id}")
async def recall_internal_message(
    message_id: str,
    current_user: User = Depends(get_current_user),
):
    """Recall (soft-delete) an internal message previously sent by the current user.

    - Only the original sender may recall their own message.
    - Recall is allowed within RECALL_WINDOW_SECONDS of the original send time;
      after that the message is locked in for audit integrity.
    - The message body is masked to a placeholder for everyone (sender included),
      and the `deleted` flag is set so clients render the tombstone uniformly.
    - Any urgent-priority alarm raised when the message was sent is automatically
      dismissed so the recipient is not left chasing a phantom alert.
    """
    msg = await db.internal_messages.find_one({
        'id': message_id,
        'tenant_id': current_user.tenant_id,
    })
    if not msg:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    if msg.get('from_user_id') != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Sadece kendi gönderdiğiniz mesajları geri alabilirsiniz",
        )
    if msg.get('deleted'):
        return {
            'success': True,
            'message_id': message_id,
            'already_deleted': True,
            'alarm_cleared': False,
        }

    # Time-window check: only the most recent messages may be recalled.
    created_at_raw = msg.get('created_at')
    created_dt = None
    try:
        if isinstance(created_at_raw, str):
            created_dt = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00'))
        elif isinstance(created_at_raw, datetime):
            created_dt = created_at_raw
        if created_dt is not None and created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=UTC)
    except Exception:
        created_dt = None

    if created_dt is not None:
        elapsed = (datetime.now(UTC) - created_dt).total_seconds()
        if elapsed > RECALL_WINDOW_SECONDS:
            minutes = RECALL_WINDOW_SECONDS // 60
            # Task #36: window-expired recall attempts are audited so a
            # tenant admin can later see "user X tried to recall a 12-min
            # old message at HH:MM and was refused". Without this row the
            # successful-recall report (Task #35) silently undercounts how
            # often staff are bumping into the 5-minute limit. We log
            # *before* raising so the audit row is committed even though
            # the response is a 400.
            try:
                preview = (msg.get('message') or '')[:200]
                recipient_label = (
                    msg.get('to_user_name')
                    or msg.get('to_user_id')
                    or msg.get('to_department')
                    or 'all_departments'
                )
                await log_audit_event(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    action="recall_internal_message_denied",
                    entity_type="internal_message",
                    entity_id=message_id,
                    details=(
                        f"Geri alma reddedildi (süre doldu): {current_user.name} "
                        f"→ {recipient_label} | yaş={int(elapsed)}s, "
                        f"limit={RECALL_WINDOW_SECONDS}s"
                    ),
                    before_value={
                        "message_id": message_id,
                        "from_user_id": msg.get('from_user_id'),
                        "to_user_id": msg.get('to_user_id'),
                        "to_department": msg.get('to_department'),
                        "priority": msg.get('priority'),
                        "created_at": created_at_raw if isinstance(created_at_raw, str) else (created_dt.isoformat() if created_dt else None),
                        "message_preview": preview,
                    },
                    after_value={
                        "denial_reason": "recall_window_expired",
                        "elapsed_seconds": int(elapsed),
                        "window_seconds": RECALL_WINDOW_SECONDS,
                    },
                    db=db,
                )
            except Exception as audit_exc:  # pragma: no cover — audit must never break the user response
                logger.warning(
                    "Failed to audit recall denial for %s: %s",
                    message_id,
                    audit_exc,
                )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Bu mesaj {minutes} dakikadan eski olduğu için geri alınamaz."
                ),
            )

    now_iso = datetime.now(UTC).isoformat()
    await db.internal_messages.update_one(
        {'id': message_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'deleted': True,
                'deleted_at': now_iso,
                'deleted_by': current_user.id,
            }
        },
    )

    # Dismiss any urgent alarm raised when this message was originally sent so
    # the alarm stack stays consistent with the (now-empty) message thread.
    alarm_cleared = False
    if msg.get('priority') == 'urgent':
        alarm_res = await db.alerts.update_many(
            {
                'tenant_id': current_user.tenant_id,
                'source_module': 'messaging',
                'source_id': message_id,
                'status': {'$ne': 'dismissed'},
            },
            {
                '$set': {
                    'status': 'dismissed',
                    'dismissed_at': now_iso,
                    'dismiss_reason': 'message_recalled',
                }
            },
        )
        alarm_cleared = (alarm_res.modified_count or 0) > 0

    # Audit trail: every recall is logged so tenant admins can later see who
    # deleted which message, when, and what the original content looked like.
    # The audit_logs collection is only exposed via tenant-admin scoped
    # endpoints (see domains/admin/router.py:get_security_audit_logs), so
    # regular users cannot read these entries back.
    original_message = msg.get('message') or ''
    message_preview = original_message[:200]
    recipient_label = (
        msg.get('to_user_name')
        or msg.get('to_user_id')
        or msg.get('to_department')
        or 'all_departments'
    )
    try:
        await log_audit_event(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="recall_internal_message",
            entity_type="internal_message",
            entity_id=message_id,
            details=(
                f"Mesaj geri alındı: {current_user.name} → {recipient_label} | "
                f"{message_preview}"
            ),
            before_value={
                "message_id": message_id,
                "from_user_id": msg.get('from_user_id'),
                "from_user_name": msg.get('from_user_name'),
                "from_department": msg.get('from_department'),
                "to_user_id": msg.get('to_user_id'),
                "to_user_name": msg.get('to_user_name'),
                "to_department": msg.get('to_department'),
                "priority": msg.get('priority'),
                "message_type": msg.get('message_type'),
                "created_at": msg.get('created_at'),
                "message_preview": message_preview,
                "message_length": len(original_message),
            },
            after_value={
                "deleted": True,
                "deleted_at": now_iso,
                "deleted_by": current_user.id,
                "deleted_by_name": current_user.name,
                "alarm_cleared": alarm_cleared,
            },
            db=db,
        )
    except Exception:
        # Audit failure must never block the recall response itself; the
        # soft-delete is already committed and is the source of truth.
        logger.exception(
            "Failed to write recall audit entry for message %s", message_id
        )

    return {
        'success': True,
        'message_id': message_id,
        'deleted_at': now_iso,
        'alarm_cleared': alarm_cleared,
    }


# ============= CONTRACTING & ALLOTMENT REPORTING =============



@router.post("/messaging/send-message")
async def send_message(
    data: SendMessageRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v92 DW: auth-only
):
    """Send a message (WhatsApp/SMS/Email) to a guest"""
    current_user = await get_current_user(credentials)

    # Verify guest exists
    guest = await db.guests.find_one({'id': data.guest_id, 'tenant_id': current_user.tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # In production, integrate with Twilio/WhatsApp Business API
    # For now, simulate sending
    message = SentMessage(
        tenant_id=current_user.tenant_id,
        guest_id=data.guest_id,
        booking_id=data.booking_id,
        message_type=data.message_type,
        recipient=data.recipient,
        message_content=data.message_content,
        status="sent"
    )

    await db.sent_messages.insert_one(message.model_dump())

    return {
        'success': True,
        'message': f'{data.message_type.value.upper()} sent successfully',
        'message_id': message.id,
        'note': 'Production integration with Twilio/WhatsApp Business API required'
    }



@router.get("/messaging/auto-messages/trigger")
async def trigger_auto_messages(
    trigger_type: AutoMessageTrigger,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Trigger automatic messages based on trigger type"""
    current_user = await get_current_user(credentials)

    messages_sent = 0

    if trigger_type == AutoMessageTrigger.PRE_ARRIVAL:
        # Find bookings with check-in tomorrow
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Pre-fetch the template once (constant per trigger)
        template = await db.message_templates.find_one({
            'tenant_id': current_user.tenant_id,
            'trigger': trigger_type.value,
            'active': True
        })
        if template:
            target_bookings = await db.bookings.find({
                'tenant_id': current_user.tenant_id,
                'check_in': {'$gte': tomorrow_start, '$lte': tomorrow_end},
                'status': {'$in': ['confirmed', 'guaranteed']}
            }).to_list(length=None)

            # Batch guests + rooms in one query each
            tb_guest_ids = [b.get('guest_id') for b in target_bookings if b.get('guest_id')]
            tb_room_ids = [b.get('room_id') for b in target_bookings if b.get('room_id')]
            tb_guests_by_id: dict = {}
            if tb_guest_ids:
                async for g in db.guests.find(
                    {'id': {'$in': tb_guest_ids}, 'tenant_id': current_user.tenant_id},
                    {'_id': 0, 'id': 1, 'name': 1, 'phone': 1},
                ):
                    tb_guests_by_id[g['id']] = g
            tb_rooms_by_id: dict = {}
            if tb_room_ids:
                async for r in db.rooms.find(
                    {'id': {'$in': tb_room_ids}, 'tenant_id': current_user.tenant_id},
                    {'_id': 0, 'id': 1, 'room_number': 1},
                ):
                    tb_rooms_by_id[r['id']] = r

            for booking in target_bookings:
                guest = tb_guests_by_id.get(booking.get('guest_id'))
                if not (guest and guest.get('phone')):
                    continue
                room = tb_rooms_by_id.get(booking.get('room_id'))
                message_content = template['message_content'].replace('{guest_name}', guest['name'])
                message_content = message_content.replace('{room_number}', room.get('room_number', 'N/A') if room else 'N/A')
                message_content = message_content.replace('{check_in_date}', booking['check_in'].strftime('%Y-%m-%d') if isinstance(booking['check_in'], datetime) else str(booking['check_in']))

                message = SentMessage(
                    tenant_id=current_user.tenant_id,
                    guest_id=guest['id'],
                    booking_id=booking['id'],
                    message_type=MessageType(template['message_type']),
                    recipient=guest['phone'],
                    message_content=message_content
                )

                await db.sent_messages.insert_one(message.model_dump())
                messages_sent += 1

    return {
        'success': True,
        'trigger_type': trigger_type.value,
        'messages_sent': messages_sent,
        'note': 'Production integration with messaging services required'
    }

# ===== 6. POS IMPROVEMENTS =====


