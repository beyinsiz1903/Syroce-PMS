"""
Guest / Messaging Domain — Pydantic Schemas
Extracted from messaging/router.py inline models.
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    booking_id: str | None = None
    message_type: MessageType
    recipient: str
    message_content: str
    status: str = "sent"
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
    variables: list[str] = []


class InternalMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    from_user_name: str
    from_department: str
    to_user_id: str | None = None
    to_user_name: str | None = None
    to_department: str | None = None
    message: str
    priority: str = "normal"
    message_type: str = "text"
    attachments: list[str] = []
    read: bool = False
    read_at: datetime | None = None
    replied_to: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
