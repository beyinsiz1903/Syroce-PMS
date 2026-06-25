"""Contact Center — WhatsApp inbound ingest bridge (Faz 1).

Pure ingest service that bridges Meta WhatsApp inbound webhook payloads into the
omnichannel Contact Center model (Conversation + Message). The webhook calls this
AFTER its own legacy write, inside a ``try/except`` — this module must therefore
be resilient: it NEVER raises out, NEVER logs PII (phone/body/name), and stays
idempotent under Meta's 24h retry storm (keyed on ``provider_message_id``).

Doktrin:
- PII at-rest YALNIZCA şifreli (envelope): arayan telefonu →
  ``caller_id_hash`` (HMAC blind-index) + ``caller_id_enc``; görünen ad →
  ``caller_display_name_enc``; mesaj gövdesi → ``body_enc``. Açık metin
  telefon/gövde/ad ASLA persist edilmez, ASLA loglanmaz.
- Tenant binding kriptografik: ``tenant_id`` webhook tarafından secret-sahibi
  ``messaging_provider_configs`` (phone_number_id eşleşmesi) üzerinden verilir —
  burada istemciden/gövdeden ASLA türetilmez.
- İdempotent: mesaj upsert'i ``(tenant_id, channel, provider_message_id)`` ile
  anahtarlanır; ``unread_count`` YALNIZCA yeni eklenen gelen mesajda artar.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from models.enums import (
    ContactCenterChannel,
    ConversationStatus,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)

_CHANNEL = ContactCenterChannel.WHATSAPP.value


def _svc():
    from security.field_encryption import get_field_encryption_service

    return get_field_encryption_service()


# ── Pure builders (DB'siz test edilebilir) ──────────────────────────


def build_caller_crypto(svc, phone: str) -> tuple[str, str]:
    """Ham telefon için ``(caller_id_hash, caller_id_enc)`` döndürür.

    ``compute_search_hash`` ham değeri kendi normalize eder (strip+lower); bu
    yüzden çağıran HAM telefonu geçmeli, asla önceden escape edilmiş değil —
    yoksa HMAC token bozulur ve blind-index eşleşmez.
    """
    phone = (phone or "").strip()
    if not phone:
        return "", ""
    return svc.compute_search_hash(phone), svc.encrypt_value(phone)


def build_inbound_message_doc(
    svc,
    *,
    tenant_id: str,
    conversation_id: str,
    provider_message_id: str,
    text_body: str,
    msg_type: str,
    now: datetime | None = None,
) -> dict:
    """Şifreli gelen ``Message`` belgesini kurar (açık-metin PII anahtarı YOK)."""
    now = now or datetime.now(UTC)
    body_enc = svc.encrypt_value(text_body) if text_body else None
    return {
        "id": str(uuid4()),
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "channel": _CHANNEL,
        "direction": MessageDirection.INBOUND.value,
        "status": MessageStatus.RECEIVED.value,
        "body_enc": body_enc,
        "sender_agent_id": None,
        "provider_message_id": provider_message_id,
        "media_refs": [],
        "error": None,
        "created_at": now,
        # msg_type PII değildir (text/image/audio/...); hata ayıklama için tutulur.
        "msg_type": msg_type or "",
    }


# ── Inbound ingest ──────────────────────────────────────────────────


async def ingest_whatsapp_inbound(
    db,
    *,
    tenant_id: str,
    phone_number_id: str,
    wa_message: dict,
    contact_name: str | None = None,
) -> None:
    """Tek bir gelen WhatsApp mesajını Contact Center'a köprüler.

    Dayanıklı: tüm hataları yutar (PII'siz loglar) — webhook'un 200-fast
    sözleşmesini ve Meta retry idempotency'sini asla bozmaz.
    """
    try:
        wa_msg_id = (wa_message or {}).get("id") or ""
        from_phone = (wa_message or {}).get("from") or ""
        msg_type = (wa_message or {}).get("type") or ""
        text_body = ((wa_message or {}).get("text") or {}).get("body", "") or ""
        if not tenant_id or not wa_msg_id or not from_phone:
            logger.warning(
                "contact-center ingest: tenant/msg-id/from eksik; atlanıyor"
            )
            return

        # 0) provider_message_id idempotency PRE-CHECK (konuşma upsert'inden ÖNCE):
        #    Meta aynı mesajı retry ederse — özellikle ilk konuşma o arada
        #    KAPANMIŞSA — conv_filter AÇIK konuşma bulamaz, yeni boş bir OPEN
        #    konuşma yaratılır ve mesaj upsert'i no-op olurdu → orphan konuşma.
        #    Mesaj zaten varsa burada idempotent biçimde çıkıyoruz: konuşma
        #    yaratılmaz, sayaç artmaz.
        if await db.contact_center_messages.find_one(
            {
                "tenant_id": tenant_id,
                "channel": _CHANNEL,
                "provider_message_id": wa_msg_id,
            },
            {"_id": 1},
        ):
            return

        svc = _svc()
        caller_id_hash, caller_id_enc = build_caller_crypto(svc, from_phone)
        now = datetime.now(UTC)

        # 1) Bu arayan için AÇIK konuşmayı bul-veya-oluştur (idempotent).
        conv_filter = {
            "tenant_id": tenant_id,
            "channel": _CHANNEL,
            "caller_id_hash": caller_id_hash,
            "status": ConversationStatus.OPEN.value,
        }
        set_on_insert = {
            "id": str(uuid4()),
            "caller_id_enc": caller_id_enc,
            "created_at": now,
            "unread_count": 0,
        }
        if contact_name:
            set_on_insert["caller_display_name_enc"] = svc.encrypt_value(contact_name)
        try:
            conv = await db.contact_center_conversations.find_one_and_update(
                conv_filter,
                {"$set": {"updated_at": now}, "$setOnInsert": set_on_insert},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Eşzamanlı ilk-mesaj / Meta-retry yarışı: partial-unique index
            # (ux_cc_conv_open_caller) iki açık konuşmayı engeller; kaybeden taraf
            # kazananın AÇIK konuşmasını okur — çift/orphan açık konuşma YOK.
            conv = await db.contact_center_conversations.find_one(conv_filter)
            if conv is None:
                # TOCTOU: kazanan konuşma bu dar pencerede kapanmış olabilir;
                # var olmayan bir id'ye mesaj yazmaktansa güvenli çık (Meta yine
                # retry eder, pre-check sonraki turda devreye girer).
                logger.warning(
                    "contact-center ingest: yarış sonrası açık konuşma yok; atlanıyor"
                )
                return
        conversation_id = (conv or {}).get("id") or set_on_insert["id"]

        # 2) provider_message_id ile idempotent gelen-mesaj upsert'i.
        msg_doc = build_inbound_message_doc(
            svc,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            provider_message_id=wa_msg_id,
            text_body=text_body,
            msg_type=msg_type,
            now=now,
        )
        res = await db.contact_center_messages.update_one(
            {
                "tenant_id": tenant_id,
                "channel": _CHANNEL,
                "provider_message_id": wa_msg_id,
            },
            {"$setOnInsert": msg_doc},
            upsert=True,
        )
        newly_inserted = res.upserted_id is not None

        # 3) Konuşma aktivitesini YALNIZCA yeni eklenen gelen mesajda güncelle
        #    (Meta retry aynı id'yi yeniden iletir → çift sayma yok).
        if newly_inserted:
            await db.contact_center_conversations.update_one(
                {"id": conversation_id, "tenant_id": tenant_id},
                {
                    "$inc": {"unread_count": 1},
                    "$set": {"last_message_at": now, "updated_at": now},
                },
            )
    except Exception:
        # Asla raise etme: PII'siz log. Webhook 200-fast kalır.
        logger.exception("contact-center WhatsApp ingest başarısız (bastırıldı)")


# ── Delivery-status sync ────────────────────────────────────────────

_META_STATUS_TO_MESSAGE = {
    "sent": MessageStatus.SENT.value,
    "delivered": MessageStatus.DELIVERED.value,
    "read": MessageStatus.READ.value,
    "failed": MessageStatus.FAILED.value,
}
_STATUS_TIMESTAMP_FIELD = {
    "sent": "sent_at",
    "delivered": "delivered_at",
    "read": "read_at",
}


def map_status(meta_status: str) -> str | None:
    """Meta teslimat durumunu Contact Center ``MessageStatus`` değerine eşler."""
    return _META_STATUS_TO_MESSAGE.get((meta_status or "").lower())


async def sync_whatsapp_status(
    db,
    *,
    tenant_id: str,
    provider_message_id: str,
    meta_status: str,
    error_message: str | None = None,
) -> None:
    """Webhook ``statuses`` geri çağrısını GİDEN Contact Center mesajına yansıtır.

    Dayanıklı: hata yutar (PII'siz log). Yalnızca bizim gönderdiğimiz (outbound)
    mesajları günceller.
    """
    try:
        mapped = map_status(meta_status)
        if not tenant_id or not provider_message_id or not mapped:
            return
        now = datetime.now(UTC)
        update: dict = {"status": mapped, "updated_at": now}
        ts_field = _STATUS_TIMESTAMP_FIELD.get((meta_status or "").lower())
        if ts_field:
            update[ts_field] = now
        if mapped == MessageStatus.FAILED.value and error_message:
            update["error"] = error_message[:500]
        await db.contact_center_messages.update_one(
            {
                "tenant_id": tenant_id,
                "channel": _CHANNEL,
                "provider_message_id": provider_message_id,
                "direction": MessageDirection.OUTBOUND.value,
            },
            {"$set": update},
        )
    except Exception:
        logger.exception(
            "contact-center WhatsApp status sync başarısız (bastırıldı)"
        )
