"""Contact Center — read-boundary DTOs (Faz 1).

Açık ALLOWLIST serileştiriciler. PII (telefon/gövde/görünen ad) YALNIZCA burada,
okuma sınırında, yetkili rol için çözülür; varsayılan olarak maskelenir; ASLA
yeniden persist edilmez. Ciphertext / blind-index / Mongo ``_id`` ASLA dönmez.
"""
from __future__ import annotations


def mask_phone(phone: str | None) -> str | None:
    """Telefonu maskeler: ülke ön eki (varsa) + son 4 hane, ortası gizli."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "•" * len(digits) if digits else None
    last4 = digits[-4:]
    prefix = phone[:3] if phone.startswith("+") else ""
    return f"{prefix}{'•' * max(2, len(digits) - 4)}{last4}"


def _dec(svc, value):
    if not value:
        return None
    try:
        return svc.decrypt_value(value)
    except Exception:
        return None


# Okuma yanıtlarında izin verilen konuşma anahtarları (regression-lock testi
# bunu tüketicilerle eşler; ciphertext/_id/_hash bu kümede ASLA yer almaz).
CONVERSATION_DTO_KEYS = frozenset(
    {
        "id",
        "channel",
        "status",
        "unread_count",
        "assigned_agent_id",
        "guest_id",
        "booking_id",
        "caller_name",
        "caller_phone_masked",
        "caller_phone",
        "last_message_at",
        "created_at",
        "updated_at",
    }
)

MESSAGE_DTO_KEYS = frozenset(
    {
        "id",
        "direction",
        "status",
        "body",
        "sender_agent_id",
        "provider_message_id",
        "created_at",
        "sent_at",
        "delivered_at",
        "read_at",
    }
)


def conversation_to_dto(doc: dict, svc, *, reveal_phone: bool = False) -> dict:
    """Konuşma belgesini allowlist DTO'ya çevirir (okuma sınırında decrypt)."""
    doc = doc or {}
    name = _dec(svc, doc.get("caller_display_name_enc"))
    phone = _dec(svc, doc.get("caller_id_enc"))
    return {
        "id": doc.get("id"),
        "channel": doc.get("channel"),
        "status": doc.get("status"),
        "unread_count": doc.get("unread_count", 0),
        "assigned_agent_id": doc.get("assigned_agent_id"),
        "guest_id": doc.get("guest_id"),
        "booking_id": doc.get("booking_id"),
        "caller_name": name,
        "caller_phone_masked": mask_phone(phone),
        # Tam numara yalnızca açıkça yetkili (MANAGE) okumada açılır.
        "caller_phone": phone if reveal_phone else None,
        "last_message_at": doc.get("last_message_at"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def message_to_dto(doc: dict, svc) -> dict:
    """Mesaj belgesini allowlist DTO'ya çevirir (gövde okuma sınırında decrypt)."""
    doc = doc or {}
    return {
        "id": doc.get("id"),
        "direction": doc.get("direction"),
        "status": doc.get("status"),
        "body": _dec(svc, doc.get("body_enc")),
        "sender_agent_id": doc.get("sender_agent_id"),
        "provider_message_id": doc.get("provider_message_id"),
        "created_at": doc.get("created_at"),
        "sent_at": doc.get("sent_at"),
        "delivered_at": doc.get("delivered_at"),
        "read_at": doc.get("read_at"),
    }
