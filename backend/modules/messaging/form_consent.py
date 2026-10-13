"""Explicit transactional WhatsApp permission; never inferred from a phone number."""
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel, StrictBool

from modules.messaging.recipient_crypto import seal_recipient
from modules.messaging.whatsapp_lifecycle import normalize_phone
from security.field_encryption import get_field_encryption_service

CONSENT_TEXT = "Rezervasyon ve konaklama bildirimlerinin WhatsApp üzerinden gönderilmesine izin veriyorum. Pazarlama izni değildir."


class WhatsAppFormConsent(BaseModel):
    whatsapp_consent: StrictBool = False
    whatsapp_consent_phone: str = ""


async def record_form_consent(db, tenant_id, phone, *, source, actor):
    try:
        phone = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(422, "WhatsApp izni için ülke koduyla geçerli telefon numarası gerekli.") from exc
    now = datetime.now(UTC).isoformat()
    # A deterministic id makes retries converge without a read/insert race.
    sealed = seal_recipient(phone)
    plus_sealed = seal_recipient("+" + phone)
    withdrawn = await db.messaging_consents.find_one({
        "tenant_id": tenant_id, "channel": "whatsapp", "status": "opt_out",
        "$or": [{"recipient_hash": {"$in": [sealed["recipient_hash"], plus_sealed["recipient_hash"]]}},
                {"recipient": {"$in": [phone, "+" + phone]}}],
    })
    if withdrawn:
        raise HTTPException(409, "Bu numara için önceki ileti reddi var. Onayı kaldırarak devam edin veya tesisin iletişim izinleri bölümünden yeni izni belgeleyin.")
    consent_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:whatsapp:transactional:{sealed['recipient_hash']}"))
    await db.messaging_consents.update_one(
        {"_id": consent_id, "tenant_id": tenant_id},
        {"$set": {**sealed, "channel": "whatsapp", "status": "opt_in",
                  "purpose": "transactional", "source": source, "updated_by": actor,
                  "updated_at": now, "evidence": CONSENT_TEXT, "text_version": "transactional-v1"},
         "$setOnInsert": {"id": consent_id, "created_at": now}},
        upsert=True,
    )
    # Deliberately do not remove an existing opt-out: delivery's deny wins.


async def record_booking_consent(db, tenant_id, guest_id, actor, enabled, expected_phone=""):
    if enabled is not True:
        return
    guest = await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id})
    if not guest:
        raise HTTPException(404, "Misafir bulunamadı")
    guest = get_field_encryption_service().decrypt_document(guest, collection="guests")
    try:
        if normalize_phone(expected_phone) != normalize_phone(guest.get("phone")):
            raise ValueError("recipient changed")
    except ValueError as exc:
        raise HTTPException(422, "İzin verilen numara misafir telefonuyla eşleşmiyor; telefonu kontrol edip yeniden onaylayın.") from exc
    await record_form_consent(db, tenant_id, guest.get("phone"), source="reservation_form", actor=actor)
