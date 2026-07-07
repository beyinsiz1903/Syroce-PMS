"""Contact Center — Faz 2 sesli çağrı durum makinesi (idempotent).

``contact_center_calls`` koleksiyonunu Twilio Voice webhook'larından besler.
Doktrin:
- Idempotency: tüm yazımlar ``(tenant_id, provider_call_sid)`` anahtarıyla atomik;
  Twilio aynı status callback'i retry etse de tek satır oluşur (partial-unique
  ``ux_cc_calls_provider_sid`` race-free garanti eder).
- PII: arayan numarası ASLA düz yazılmaz → ``caller_id_hash`` (HMAC blind-index) +
  ``caller_id_enc`` (zarf-şifreli). recording_ref yalnızca nesne-deposu anahtarı.
- Dayanıklı: hatalar yutulur (PII'siz log) — webhook 200-fast sözleşmesini bozmaz.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from domains.contact_center.whatsapp_ingest import build_caller_crypto
from models.enums import CallStatus, ContactCenterChannel, MessageDirection

logger = logging.getLogger(__name__)

_COLLECTION = "contact_center_calls"
_CHANNEL = ContactCenterChannel.VOICE.value

# Twilio CallStatus → iç CallStatus eşlemesi (bilinmeyen = değişiklik yapma).
_TWILIO_STATUS_MAP: dict[str, CallStatus] = {
    "queued": CallStatus.RINGING,
    "initiated": CallStatus.RINGING,
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.ANSWERED,
    "answered": CallStatus.ANSWERED,
    "completed": CallStatus.COMPLETED,
    "busy": CallStatus.MISSED,
    "no-answer": CallStatus.MISSED,
    "canceled": CallStatus.FAILED,
    "failed": CallStatus.FAILED,
}

_TERMINAL = {CallStatus.COMPLETED, CallStatus.MISSED, CallStatus.FAILED}


def _svc():
    from security.field_encryption import get_field_encryption_service

    return get_field_encryption_service()


def map_twilio_status(twilio_status: str | None) -> CallStatus | None:
    if not twilio_status:
        return None
    return _TWILIO_STATUS_MAP.get(twilio_status.strip().lower())


async def _record_call(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    phone: str,
    direction: str,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    parent_call_sid: str | None = None,
    call_attempt_id: str | None = None,
) -> str | None:
    """Gelen/giden çağrıyı idempotent biçimde kaydeder; çağrı ``id``'sini döner.

    ``(tenant_id, provider_call_sid)`` üzerinde upsert: Twilio aynı webhook'u retry
    etse de tek satır oluşur. Telefon (gelen=arayan, giden=hedef) yalnızca hash+enc
    tutulur — düz metin ASLA saklanmaz.
    """
    if not tenant_id or not provider_call_sid:
        logger.warning("[CC-VOICE] kayıt: tenant/call-sid eksik; atlanıyor")
        return None
    try:
        # Check call_attempt_id idempotency first
        if tenant_id and agent_id and call_attempt_id:
            existing = await db[_COLLECTION].find_one({
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "call_attempt_id": call_attempt_id
            })
            if existing:
                return existing["id"]

        svc = _svc()
        caller_id_hash, caller_id_enc = build_caller_crypto(svc, phone or "")
        now = datetime.now(UTC)
        set_on_insert = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "provider_call_sid": provider_call_sid,
            "parent_call_sid": parent_call_sid,
            "conversation_id": conversation_id,
            "channel": _CHANNEL,
            "direction": direction,
            "status": CallStatus.RINGING.value,
            "caller_id_hash": caller_id_hash,
            "caller_id_enc": caller_id_enc,
            "agent_id": agent_id,
            "call_attempt_id": call_attempt_id,
            "recording_ref": None,
            "duration_seconds": 0,
            "disposition": None,
            "started_at": now,
            "answered_at": None,
            "ended_at": None,
        }

        # CRM Lookup: Arayan numarayı Guests tablosunda bul ve adını kaydet
        if phone:
            try:
                from security.encrypted_lookup import build_guest_pii_query, decrypt_guest_doc
                guest_doc = await db.guests.find_one({"tenant_id": tenant_id, **build_guest_pii_query("phone", phone)})
                if guest_doc:
                    guest_doc = decrypt_guest_doc(guest_doc)
                    name = guest_doc.get("name") or f"{guest_doc.get('first_name', '')} {guest_doc.get('last_name', '')}".strip()
                    if name:
                        set_on_insert["caller_name_enc"] = svc.encrypt_value(name)
            except Exception as e:
                logger.debug("[CC-VOICE] CRM misafir araması başarısız: %s", e)

        try:
            doc = await db[_COLLECTION].find_one_and_update(
                {"tenant_id": tenant_id, "provider_call_sid": provider_call_sid},
                {"$setOnInsert": set_on_insert},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            doc = await db[_COLLECTION].find_one({"tenant_id": tenant_id, "provider_call_sid": provider_call_sid})
        return (doc or {}).get("id") or set_on_insert["id"]
    except Exception:
        logger.exception("[CC-VOICE] çağrı kaydı başarısız (bastırıldı, PII'siz)")
        return None


async def record_inbound_call(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    from_phone: str,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    parent_call_sid: str | None = None,
) -> str | None:
    """Gelen çağrıyı idempotent biçimde kaydeder (arayan numarası hash+enc)."""
    return await _record_call(
        db,
        tenant_id=tenant_id,
        provider_call_sid=provider_call_sid,
        phone=from_phone,
        direction=MessageDirection.INBOUND.value,
        agent_id=agent_id,
        conversation_id=conversation_id,
        parent_call_sid=parent_call_sid,
    )


async def record_outbound_call(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    to_phone: str,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    parent_call_sid: str | None = None,
    call_attempt_id: str | None = None,
) -> str | None:
    """Giden (click-to-dial) çağrıyı idempotent kaydeder (hedef numarası hash+enc).

    Gelen çağrıyla aynı koleksiyon/anahtar/şifreleme boru hattını kullanır; tek fark
    ``direction=outbound`` ve telefonun aranan (hedef) numara olmasıdır.
    """
    return await _record_call(
        db,
        tenant_id=tenant_id,
        provider_call_sid=provider_call_sid,
        phone=to_phone,
        direction=MessageDirection.OUTBOUND.value,
        agent_id=agent_id,
        conversation_id=conversation_id,
        parent_call_sid=parent_call_sid,
        call_attempt_id=call_attempt_id,
    )


async def update_call_status(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    twilio_status: str,
    duration_seconds: int | None = None,
    parent_call_sid: str | None = None,
) -> bool:
    """Twilio status callback'ini iç duruma yansıtır (idempotent).

    Terminal duruma geçişte ``ended_at``, yanıtlanmada ``answered_at`` set edilir.
    Bilinmeyen status'te değişiklik yapılmaz (fail-safe).
    """
    if not tenant_id or not provider_call_sid:
        return False
    mapped = map_twilio_status(twilio_status)
    if mapped is None:
        logger.warning("[CC-VOICE] bilinmeyen twilio status; atlanıyor")
        return False
    now = datetime.now(UTC)
    set_fields: dict = {"status": mapped.value, "updated_at": now}
    if parent_call_sid:
        set_fields["parent_call_sid"] = parent_call_sid
    if mapped == CallStatus.ANSWERED:
        set_fields["answered_at"] = now
    if mapped in _TERMINAL:
        set_fields["ended_at"] = now
    if duration_seconds is not None and duration_seconds >= 0:
        set_fields["duration_seconds"] = int(duration_seconds)
    try:
        res = await db[_COLLECTION].update_one(
            {"tenant_id": tenant_id, "provider_call_sid": provider_call_sid},
            {"$set": set_fields},
        )
        return bool(getattr(res, "matched_count", 0))
    except Exception:
        logger.exception("[CC-VOICE] status güncelleme başarısız (bastırıldı)")
        return False


async def attach_recording_ref(
    db,
    *,
    tenant_id: str,
    provider_call_sid: str,
    recording_ref: str,
    duration_seconds: int | None = None,
) -> bool:
    """Şifrelenip yüklenmiş kaydın nesne-deposu anahtarını çağrıya bağlar.

    Yalnızca ``recording_ref`` (anahtar) saklanır — imzalı URL ASLA persist edilmez.
    """
    if not tenant_id or not provider_call_sid or not recording_ref:
        return False
    set_fields: dict = {
        "recording_ref": recording_ref,
        "updated_at": datetime.now(UTC),
    }
    if duration_seconds is not None and duration_seconds >= 0:
        set_fields["duration_seconds"] = int(duration_seconds)
    try:
        res = await db[_COLLECTION].update_one(
            {"tenant_id": tenant_id, "provider_call_sid": provider_call_sid},
            {"$set": set_fields},
        )
        return bool(getattr(res, "matched_count", 0))
    except Exception:
        logger.exception("[CC-VOICE] recording_ref bağlama başarısız (bastırıldı)")
        return False
