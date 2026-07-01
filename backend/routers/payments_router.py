"""Saglayici-bagimsiz odeme endpoint'leri (operator tahsilat + webhook).

Doktrin:
- Tenant'in aktif saglayicisi registry'den fail-closed secilir (yoksa 503).
- PSP cagrisi (harici I/O) Mongo transaction'ina GIREMEZ: once intent(pending),
  sonra PSP, basari halinde sonuc atomik yazilir (payment + folio + booking +
  intent + idempotency completion tek tx).
- Tahsilat sonucu belirsiz (5xx) ise intent 'unknown' kalir, kilit birakilmaz;
  mutabakat (reconcile) worker'i (Task #313) cozumler.
- Webhook HMAC ile dogrulanir (fail-closed), tenant conversationId->intent'ten
  KRIPTOGRAFIK olarak turetilir (client input degil), olaylar idempotent islenir.
- Ham PAN/CVV/secret/imza ASLA loglanmaz; yanit yalnizca maskeli kart tasir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import core.payments.providers  # noqa: F401  (import-time provider kaydi)
from core.database import db
from core.payments import (
    PaymentError,
    get_provider_for_tenant,
    make_vault_card_ref,
)
from core.payments.collection import collect_booking_payment
from core.security import get_current_user
from models.enums import PaymentType
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.idempotency import ensure_idempotent_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])


class CollectPaymentRequest(BaseModel):
    amount: float
    currency: str = "TRY"
    vault_card_ref: str | None = None
    payment_type: PaymentType = PaymentType.INTERIM
    descriptor: str | None = None
    metadata: dict = {}


def _to_minor(amount: float) -> int:
    """Major (TL) tutari kurus-tam integer'e cevir (Decimal, float aritmetigi yok)."""
    q = (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(q)


def _source_ip(request: Request) -> str:
    try:
        client = getattr(request, "client", None)
        return client.host if client else "unknown"
    except Exception:
        return "unknown"


@router.post("/collect/{booking_id}")
async def collect_payment(
    booking_id: str,
    body: CollectPaymentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),
):
    """Operator-tetikli kart tahsilati (VCC/kasa karti uzerinden).

    Idempotency-Key zorunlu (cift-tiklama/retry replay korumasi). Tahsilat
    basariyla gerceklesirse folio payment + bakiye + booking.paid_amount atomik
    yazilir ve provider_ref kayda baglanir.
    """
    tenant_id = current_user.tenant_id
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount 0'dan buyuk olmali")
    idem_key = ensure_idempotent_request(request, required=True)
    amount_minor = _to_minor(body.amount)

    # Saglayici fail-closed (yoksa/yapilandirilmamissa 503 not_configured).
    try:
        provider = await get_provider_for_tenant(db, tenant_id)
    except PaymentError as pe:
        raise HTTPException(status_code=pe.http_status, detail=pe.error_code)

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    folio = await db.folios.find_one(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "status": "open",
            "folio_type": "guest",
        },
        {"_id": 0},
    )
    if not folio:
        raise HTTPException(status_code=404, detail="Acik folyo bulunamadi")

    vault_ref = body.vault_card_ref
    if not vault_ref:
        card = await db.vcc_cards.find_one({"booking_id": booking_id, "tenant_id": tenant_id}, {"_id": 0, "id": 1})
        if not card:
            raise HTTPException(status_code=404, detail="Booking icin kasa karti yok")
        vault_ref = make_vault_card_ref(card["id"])

    # Tahsilat cekirdegi tek dogruluk kaynagindan calisir (endpoint + otonom worker
    # ayni durum makinesini paylasir). Servis HTTPException atmaz; yapisal outcome
    # doner ve burada HTTP'ye eslenir (#312 davranisi birebir korunur).
    outcome = await collect_booking_payment(
        db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        folio=folio,
        amount_minor=amount_minor,
        currency=body.currency,
        vault_ref=vault_ref,
        idempotency_key=idem_key,
        scope=f"payment_collect:{booking_id}",
        payment_type=body.payment_type.value,
        processed_by=current_user.name,
        descriptor=body.descriptor,
        metadata=dict(body.metadata or {}),
        provider=provider,
    )

    if outcome.status == "replay":
        return outcome.response
    if outcome.status == "in_flight":
        raise HTTPException(status_code=409, detail=outcome.detail)
    if outcome.status == "requires_action":
        return {
            "status": "requires_action",
            "intent_id": outcome.intent_id,
            "requires_action_url": outcome.requires_action_url,
        }
    if outcome.status in ("failed", "unknown", "not_configured"):
        raise HTTPException(status_code=outcome.http_status, detail=outcome.detail)
    # paid + paid_unrecorded: PSP tahsil etti -> basari yaniti don (kayit yazilamadiysa
    # intent reconcile'a kalir; para alindigi icin client'a basari bildirilir).
    return outcome.response


# ── Webhook (3DS/async sonuc mutabakati) ──────────────────────────


def _webhook_secret() -> str | None:
    secret = os.getenv("IYZICO_WEBHOOK_SECRET")
    return secret if secret else None


@router.post("/webhook/iyzico")
async def iyzico_webhook(request: Request):
    """Iyzico async/3DS bildirimi.

    Fail-closed: secret yoksa 503; imza gecersizse 401. Tenant, conversationId
    -> payment_intents kaydindan turetilir (client input ASLA guvenilmez). Ayni
    olay idempotent islenir. Secret/imza/PAN loglanmaz.
    """
    raw = await request.body()
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="webhook not configured")

    provided = request.headers.get("X-IYZ-SIGNATURE") or request.headers.get("X-Iyz-Signature") or ""
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not provided or not hmac.compare_digest(expected, provided.strip().lower()):
        logger.warning(
            "[IYZICO-WEBHOOK][SECURITY] reject reason=bad_signature source_ip=%s",
            _source_ip(request),
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid body")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid body")

    conversation_id = payload.get("conversationId") or payload.get("token")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversationId required")

    # Tenant binding: conversationId == bizim SUNUCU-URETIMI conversation_token'imiz
    # -> intent. Token globally-unique + unique-index ile zorlanir; client bir
    # baska tenant'in token'ini tahmin/forge edemeyeceginden tenant guvenle turetilir.
    intent = await db.payment_intents.find_one({"conversation_token": conversation_id}, {"_id": 0})
    if not intent:
        # Bize ait olmayan/eski olay: sessizce kabul et (retry firtinasi olmasin).
        return {"status": "ignored"}
    tenant_id = intent["tenant_id"]

    # Olay dedup (idempotent ingest): _id tekilligi.
    event_key = hashlib.sha256(f"{tenant_id}:{conversation_id}:{payload.get('paymentId') or ''}:{payload.get('iyziEventType') or payload.get('status') or ''}".encode()).hexdigest()
    from pymongo.errors import DuplicateKeyError  # type: ignore

    try:
        await db.payment_webhook_events.insert_one(
            {
                "_id": event_key,
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
    except DuplicateKeyError:
        return {"status": "duplicate"}

    status_raw = str(payload.get("status") or "")
    webhook_status = "webhook_success" if status_raw == "success" else "webhook_failed"
    await db.payment_intents.update_one(
        {"id": intent["id"], "tenant_id": tenant_id},
        {
            "$set": {
                "webhook_status": webhook_status,
                "webhook_provider_ref": str(payload.get("paymentId") or "") or None,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    return {"status": "processed", "intent_status": webhook_status}
