"""
Guest / Messaging Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.schemas import SendEmailRequest, SendSMSRequest, SendWhatsAppRequest, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Guest / Messaging"])


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
    booking_id: Optional[str] = None

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
    booking_id: Optional[str] = None
    message_type: MessageType
    recipient: str  # phone or email
    message_content: str
    status: str = "sent"  # sent, delivered, failed
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    template_name: str
    message_type: MessageType
    trigger: AutoMessageTrigger
    message_content: str
    active: bool = True
    variables: List[str] = []  # e.g., ['{guest_name}', '{room_number}', '{check_in_date}']


class InternalMessage(BaseModel):
    """Internal messaging between departments"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    from_user_name: str
    from_department: str
    to_user_id: Optional[str] = None  # None = broadcast to department
    to_user_name: Optional[str] = None
    to_department: Optional[str] = None  # None = all departments
    message: str
    priority: str = "normal"  # low, normal, high, urgent
    message_type: str = "text"  # text, task, alert, announcement
    attachments: List[str] = []
    read: bool = False
    read_at: Optional[datetime] = None
    replied_to: Optional[str] = None  # Original message ID if this is a reply
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.post("/whatsapp/send-confirmation")
async def send_whatsapp_confirmation(
    booking_id: str,
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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
        'sent_at': datetime.now(timezone.utc).isoformat(),
        'sent_by': current_user.id
    }

    msg_copy = msg_record.copy()
    await db.messages.insert_one(msg_copy)
    return {'message': 'WhatsApp message sent successfully', 'message_id': msg_record['id']}



@router.post("/messaging/send-email")
async def send_email_message(
    request: SendEmailRequest,
    current_user: User = Depends(get_current_user)
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
        'sent_at': datetime.now(timezone.utc).isoformat(),
        'sent_by': current_user.id
    }

    msg_copy = msg_record.copy()
    await db.messages.insert_one(msg_copy)
    return {'message': 'Email sent successfully', 'message_id': msg_record['id']}



@router.post("/messaging/send-sms")
async def send_sms_message(
    request: SendSMSRequest,
    current_user: User = Depends(get_current_user)
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
        'sent_at': datetime.now(timezone.utc).isoformat(),
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
    to_department: Optional[str] = None,
    to_user_id: Optional[str] = None,
    priority: str = "normal",
    message_type: str = "text",
    current_user: User = Depends(get_current_user)
):
    """
    Send internal message
    - Department to department (e.g., Reception → HK)
    - Department to specific user (e.g., HK → Maintenance tech)
    - Broadcast to all (e.g., GM → All departments)
    """
    # Get to_user info if specified
    to_user_name = None
    if to_user_id:
        to_user = await db.users.find_one({'id': to_user_id})
        to_user_name = to_user.get('name') if to_user else None

    # Determine from_department based on user role
    department_mapping = {
        'front_desk': 'Reception',
        'housekeeping': 'Housekeeping',
        'maintenance': 'Maintenance',
        'finance': 'Finance',
        'supervisor': 'Management',
        'admin': 'Management'
    }
    from_department = department_mapping.get(current_user.role.value, 'General')

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

    # Create alert for urgent messages
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
            'created_at': datetime.now(timezone.utc).isoformat()
        })

    return {
        'success': True,
        'message_id': message_obj.id,
        'delivered_to': to_user_name or to_department or 'All departments'
    }




@router.get("/messaging/internal/inbox")
async def get_internal_messages_inbox(
    department: Optional[str] = None,
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

    if unread_only:
        match_criteria['read'] = False

    if department:
        match_criteria['from_department'] = department

    messages = []
    async for msg in db.internal_messages.find(match_criteria).sort('created_at', -1).limit(limit):
        messages.append({
            'id': msg.get('id'),
            'from_user_name': msg.get('from_user_name'),
            'from_department': msg.get('from_department'),
            'to_user_name': msg.get('to_user_name'),
            'to_department': msg.get('to_department') or 'All',
            'message': msg.get('message'),
            'priority': msg.get('priority'),
            'message_type': msg.get('message_type'),
            'read': msg.get('read'),
            'created_at': msg.get('created_at'),
            'time_ago': calculate_time_ago(msg.get('created_at'))
        })

    unread_count = await db.internal_messages.count_documents({
        **match_criteria,
        'read': False
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
    """Mark internal message as read"""
    await db.internal_messages.update_one(
        {'id': message_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'read': True,
            'read_at': datetime.now(timezone.utc).isoformat()
        }}
    )

    return {'success': True, 'message': 'Message marked as read'}




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
        messages.append({
            'id': msg.get('id'),
            'from_user_id': msg.get('from_user_id'),
            'from_user_name': msg.get('from_user_name'),
            'message': msg.get('message'),
            'priority': msg.get('priority'),
            'created_at': msg.get('created_at'),
            'is_from_me': msg.get('from_user_id') == current_user.id
        })

    return {
        'user_id': user_id,
        'message_count': len(messages),
        'messages': messages
    }


# ============= CONTRACTING & ALLOTMENT REPORTING =============



@router.post("/messaging/send-message")
async def send_message(
    data: SendMessageRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)

        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$gte': tomorrow_start, '$lte': tomorrow_end},
            'status': {'$in': ['confirmed', 'guaranteed']}
        }):
            # Get guest
            guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id})
            if guest and guest.get('phone'):
                # Get template
                template = await db.message_templates.find_one({
                    'tenant_id': current_user.tenant_id,
                    'trigger': trigger_type.value,
                    'active': True
                })

                if template:
                    # Replace variables
                    room = await db.rooms.find_one({'id': booking['room_id'], 'tenant_id': current_user.tenant_id})
                    message_content = template['message_content'].replace('{guest_name}', guest['name'])
                    message_content = message_content.replace('{room_number}', room.get('room_number', 'N/A') if room else 'N/A')
                    message_content = message_content.replace('{check_in_date}', booking['check_in'].strftime('%Y-%m-%d') if isinstance(booking['check_in'], datetime) else str(booking['check_in']))

                    # Send message
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


