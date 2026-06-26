"""Syroce Contact Center — omnichannel iletişim şemaları (Faz 0).

Çağrı merkezi / omnichannel modülünün veritabanı belge modelleri.

Doktrin:
- Kiracı izolasyonu: her belgede ``tenant_id`` zorunlu.
- PII at-rest açık metin YOK. Arayan telefonu HMAC blind-index
  (``caller_id_hash``) ile aranır ve zarf-şifreli alanda (``caller_id_enc``)
  saklanır; çözme yalnızca read-boundary'de yapılır, asla yeniden persist
  edilmez. Mesaj gövdesi de şifreli (``body_enc``) tutulur.
- Bu Faz 0 iskeletidir: gerçek transport (WhatsApp Cloud API, Twilio,
  on-prem PBX) bağlı DEĞİL — sağlayıcı katmanı mock + fail-closed çalışır.
"""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    CallStatus,
    ContactCenterChannel,
    ConversationStatus,
    MessageDirection,
    MessageStatus,
)


class Conversation(BaseModel):
    """Omnichannel konuşma başlığı (WhatsApp/voice/web/social/email)."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel: ContactCenterChannel
    status: ConversationStatus = ConversationStatus.OPEN
    # Arayan kimliği — açık metin telefon SAKLANMAZ.
    # caller_id_hash: HMAC blind-index (arama için); caller_id_enc: zarf-şifreli.
    caller_id_hash: str | None = None
    caller_id_enc: str | None = None
    # Görünen ad PII'dir → açık metin SAKLANMAZ; zarf-şifreli tutulur ve yalnızca
    # read-boundary'de (Faz 1, bilinçli maskeleme/çözme ile) açılır.
    caller_display_name_enc: str | None = None
    guest_id: str | None = None
    booking_id: str | None = None
    assigned_agent_id: str | None = None
    unread_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Message(BaseModel):
    """Konuşma içindeki tekil mesaj (gelen/giden)."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    conversation_id: str
    channel: ContactCenterChannel
    direction: MessageDirection
    status: MessageStatus = MessageStatus.QUEUED
    # Mesaj gövdesi PII içerebilir → açık metin SAKLANMAZ (zarf-şifreli).
    body_enc: str | None = None
    # Giden mesajda gönderen personel id'si; gelen mesajda None ("guest").
    sender_agent_id: str | None = None
    # Sağlayıcının döndürdüğü mesaj kimliği (idempotency/teslimat takibi).
    provider_message_id: str | None = None
    # Faz 2: medya/ses kaydı YALNIZCA object-storage referansı; URL loglanmaz.
    media_refs: list[str] = []
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None


class CallLog(BaseModel):
    """Sesli çağrı kaydı (Faz 2'de PBX/Twilio Voice ile dolacak)."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    conversation_id: str | None = None
    channel: ContactCenterChannel = ContactCenterChannel.VOICE
    direction: MessageDirection
    status: CallStatus = CallStatus.RINGING
    # Faz 2: Twilio CallSid — (tenant_id, provider_call_sid) idempotency anahtarı.
    # Twilio status/recording callback'leri retry edildiğinde tek satır garanti eder.
    provider_call_sid: str | None = None
    caller_id_hash: str | None = None
    caller_id_enc: str | None = None
    agent_id: str | None = None
    # Faz 2: ses kaydı YALNIZCA object-storage referansı; imzalı URL asla loglanmaz.
    recording_ref: str | None = None
    duration_seconds: int = 0
    disposition: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    answered_at: datetime | None = None
    ended_at: datetime | None = None
