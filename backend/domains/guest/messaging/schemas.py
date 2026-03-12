"""
Guest / Messaging Domain — Pydantic Schemas
Extracted from messaging/router.py inline models.
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
import uuid


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

    @field_validator("message_type", mode="before")
    @classmethod
    def lowercase_message_type(cls, v):
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
    recipient: str
    message_content: str
    status: str = "sent"
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
    variables: List[str] = []


class InternalMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    from_user_name: str
    from_department: str
    to_user_id: Optional[str] = None
    to_user_name: Optional[str] = None
    to_department: Optional[str] = None
    message: str
    priority: str = "normal"
    message_type: str = "text"
    attachments: List[str] = []
    read: bool = False
    read_at: Optional[datetime] = None
    replied_to: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
