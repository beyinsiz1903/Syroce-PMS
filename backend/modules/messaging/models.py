"""
Data models for the messaging module.
Channels: Email (SMTP) and WhatsApp (Meta Business API).
"""
import uuid
from datetime import UTC, datetime
from enum import Enum


class ProviderType(str, Enum):
    SMTP_EMAIL = "smtp_email"
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
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class ConsentStatus(str, Enum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    PENDING = "pending"


class TemplateCategory(str, Enum):
    HOSGELDINIZ = "hosgeldiniz"
    YOL_TARIFI = "yol_tarifi"
    TESIS_BILGI = "tesis_bilgi"
    FATURA = "fatura"
    KAMPANYA = "kampanya"
    PUAN_DEGERLENDIRME = "puan_degerlendirme"
    CHECKOUT = "checkout"
    REZERVASYON_ONAY = "rezervasyon_onay"
    ILETISIM = "iletisim"
    GENEL = "genel"


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
