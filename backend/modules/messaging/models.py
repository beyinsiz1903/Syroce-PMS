"""
Data models for the messaging module.
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel


class ProviderType(str, Enum):
    TWILIO_SMS = "twilio_sms"
    SENDGRID_EMAIL = "sendgrid_email"
    WHATSAPP = "whatsapp"


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    REJECTED = "rejected"


class MessageChannel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class ConsentStatus(str, Enum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    PENDING = "pending"


class TemplateCategory(str, Enum):
    PRE_ARRIVAL = "pre_arrival"
    CHECK_IN = "check_in"
    ROOM_READY = "room_ready"
    GUEST_REQUEST_ACK = "guest_request_ack"
    CHECKOUT_THANKYOU = "checkout_thankyou"
    REVIEW_REQUEST = "review_request"
    MARKETING = "marketing"
    ALERT = "alert"


# ── Document shapes for MongoDB ──

def new_provider_config(
    tenant_id: str,
    provider_type: str,
    credentials: dict,
    is_sandbox: bool = False,
    enabled: bool = True,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "provider_type": provider_type,
        "credentials_encrypted": credentials,
        "is_sandbox": is_sandbox,
        "enabled": enabled,
        "health_status": "unknown",
        "last_health_check": None,
        "rate_limit_per_minute": 60,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def new_delivery_log(
    tenant_id: str,
    property_id: str | None,
    channel: str,
    provider_type: str,
    recipient: str,
    template_id: str | None,
    subject: str | None,
    body: str,
    booking_id: str | None = None,
    guest_id: str | None = None,
    use_case: str | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "channel": channel,
        "provider_type": provider_type,
        "recipient": recipient,
        "template_id": template_id,
        "subject": subject,
        "body": body,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "use_case": use_case,
        "status": DeliveryStatus.QUEUED.value,
        "provider_message_id": None,
        "error_message": None,
        "retry_count": 0,
        "max_retries": 3,
        "next_retry_at": None,
        "delivered_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def new_message_template(
    tenant_id: str,
    name: str,
    category: str,
    channel: str,
    subject: str | None,
    body_template: str,
    variables: list,
    version: int = 1,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": name,
        "category": category,
        "channel": channel,
        "subject": subject,
        "body_template": body_template,
        "variables": variables,
        "version": version,
        "is_active": True,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


# ── Pydantic request/response models ──

class ProviderConfigCreate(BaseModel):
    provider_type: ProviderType
    credentials: dict[str, str]
    is_sandbox: bool = False
    enabled: bool = True

class ProviderConfigUpdate(BaseModel):
    credentials: dict[str, str] | None = None
    is_sandbox: bool | None = None
    enabled: bool | None = None

class TemplateCreate(BaseModel):
    name: str
    category: TemplateCategory
    channel: MessageChannel
    subject: str | None = None
    body_template: str
    variables: list[str] = []

class TemplateUpdate(BaseModel):
    subject: str | None = None
    body_template: str | None = None
    variables: list[str] | None = None
    is_active: bool | None = None

class SendMessageRequest(BaseModel):
    channel: MessageChannel
    recipient: str
    template_id: str | None = None
    subject: str | None = None
    body: str | None = None
    variables: dict[str, str] = {}
    booking_id: str | None = None
    guest_id: str | None = None
    property_id: str | None = None
    use_case: str | None = None
