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
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.booking_atomicity import is_replica_set_unavailable, standalone_fallback_allowed
from core.database import db
from core.payments import (
    PaymentError,
    PaymentOperation,
    PaymentRequest,
    PaymentStatus,
    get_provider_for_tenant,
    make_vault_card_ref,
)
import core.payments.providers  # noqa: F401  (import-time provider kaydi)
from core.security import get_current_user
from models.enums import PaymentType
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    ensure_idempotent_request,
    release_idempotency,
)

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
    amount_major = round(amount_minor / 100.0, 2)

    # Saglayici fail-closed (yoksa/yapilandirilmamissa 503 not_configured).
    try:
        provider = await get_provider_for_tenant(db, tenant_id)
    except PaymentError as pe:
        raise HTTPException(status_code=pe.http_status, detail=pe.error_code)

    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
    )
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
        card = await db.vcc_cards.find_one(
            {"booking_id": booking_id, "tenant_id": tenant_id}, {"_id": 0, "id": 1}
        )
        if not card:
            raise HTTPException(
                status_code=404, detail="Booking icin kasa karti yok"
            )
        vault_ref = make_vault_card_ref(card["id"])

    # Idempotency claim (replay/in-flight).
    claim = await claim_idempotency(
        db,
        tenant_id=tenant_id,
        scope=f"payment_collect:{booking_id}",
        idempotency_key=idem_key,
    )
    if claim["status"] == "replay":
        return claim["response"]
    if claim["status"] == "in_flight":
        raise HTTPException(
            status_code=409,
            detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
        )
    lock_id = claim["lock_id"]

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    intent_id = str(uuid.uuid4())
    # conversation_token: SUNUCU-URETIMI, globally-unique korelasyon kimligi. PSP'ye
    # conversationId olarak BU gonderilir; webhook tenant binding'i bunun uzerinden
    # yapilir. Client-controlled idem_key tenant'lar arasi cakisabildiginden ASLA
    # PSP korelasyonu/webhook lookup'i icin kullanilmaz.
    conversation_token = uuid.uuid4().hex
    await db.payment_intents.insert_one(
        {
            "id": intent_id,
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "folio_id": folio["id"],
            "idempotency_key": idem_key,
            "conversation_token": conversation_token,
            "provider": provider.name,
            "operation": PaymentOperation.CHARGE.value,
            "amount_minor": amount_minor,
            "currency": body.currency.upper(),
            "status": "pending",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    )

    pay_req = PaymentRequest(
        operation=PaymentOperation.CHARGE,
        tenant_id=tenant_id,
        currency=body.currency,
        idempotency_key=conversation_token,
        amount_minor=amount_minor,
        vault_card_ref=vault_ref,
        booking_id=booking_id,
        descriptor=body.descriptor,
        metadata=dict(body.metadata or {}),
    )

    # ── PSP cagrisi (transaction DISINDA) ─────────────────────────
    try:
        result = await provider.charge(pay_req)
    except PaymentError as pe:
        # 5xx -> durum belirsiz: intent 'unknown', kilit BIRAKILMAZ (reconcile).
        # 4xx -> kesin hata: intent 'failed', kilit birakilir (retry serbest).
        unknown = pe.http_status >= 500
        await db.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "unknown" if unknown else "failed",
                "error_code": pe.error_code,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        if not unknown:
            await release_idempotency(db, lock_id=lock_id)
        raise HTTPException(status_code=pe.http_status, detail=pe.error_code)
    except Exception:
        # Beklenmeyen: durum belirsiz kabul edilir (cift-charge riski) -> kilit tut.
        await db.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {"status": "unknown", "updated_at": datetime.now(UTC).isoformat()}},
        )
        logger.exception("tahsilat sirasinda beklenmeyen hata (durum belirsiz)")
        raise HTTPException(status_code=502, detail="tahsilat durumu belirsiz")

    if result.status == PaymentStatus.REQUIRES_ACTION:
        # 3DS yonlendirmesi gerekli: intent acik kalir, webhook/worker tamamlar.
        await db.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "requires_action",
                "provider_ref": result.provider_ref,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        await release_idempotency(db, lock_id=lock_id)
        return {
            "status": "requires_action",
            "intent_id": intent_id,
            "requires_action_url": result.requires_action_url,
        }

    if not result.ok:
        await db.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "failed",
                "error_code": result.error_code,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        await release_idempotency(db, lock_id=lock_id)
        raise HTTPException(
            status_code=402,
            detail=result.error_message or "tahsilat reddedildi",
        )

    # ── Basari: sonucu atomik yaz ─────────────────────────────────
    payment_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": amount_major,
        "method": "card",
        "payment_type": body.payment_type.value,
        "status": "paid",
        "voided": False,
        "reference": result.provider_ref,
        "provider": provider.name,
        "provider_ref": result.provider_ref,
        "provider_txn_ref": result.provider_txn_ref,
        "masked_card": result.masked_card,
        "idempotency_key": idem_key,
        "processed_by": current_user.name,
        "processed_at": now_iso,
    }
    response = {
        "id": payment_doc["id"],
        "status": "paid",
        "amount": amount_major,
        "provider": provider.name,
        "provider_ref": result.provider_ref,
        "masked_card": result.masked_card,
        "intent_id": intent_id,
    }

    async def _record(session=None):
        await db.payments.insert_one(dict(payment_doc), session=session)
        await db.folios.update_one(
            {"id": folio["id"], "tenant_id": tenant_id},
            {"$inc": {"balance": -amount_major}},
            session=session,
        )
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"$inc": {"paid_amount": amount_major}},
            session=session,
        )
        await db.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "completed",
                "provider_ref": result.provider_ref,
                "payment_id": payment_doc["id"],
                "updated_at": datetime.now(UTC).isoformat(),
            }},
            session=session,
        )

    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                await _record(session=session)
                await complete_idempotency(
                    db, lock_id=lock_id, response_body=response, session=session
                )
        lock_id = None
    except Exception as exc:  # noqa: BLE001
        # PSP zaten tahsil etti -> kaydi KAYBETMEK en kotu sonuc. Yalnizca
        # replica-set yoksa VE operator env ile acikca izin verdiyse (dev standalone)
        # tx'siz best-effort kaydet; aksi halde fail-closed: intent'i mutabakata
        # isaretleyip basari yanitini yine de don (para alindi, kayit reconcile'a).
        if is_replica_set_unavailable(exc) and standalone_fallback_allowed():
            await _record(session=None)
            try:
                await complete_idempotency(
                    db, lock_id=lock_id, response_body=response
                )
            except Exception:  # noqa: BLE001
                logger.exception("idempotency complete failed (non-tx fallback)")
            lock_id = None
        else:
            logger.exception(
                "tahsilat kaydi atomik yazilamadi; intent reconcile'a birakildi"
            )
            await db.payment_intents.update_one(
                {"id": intent_id, "tenant_id": tenant_id},
                {"$set": {
                    "status": "completed_unrecorded",
                    "provider_ref": result.provider_ref,
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            # Kilidi birakma: tekrar denenirse cift-charge yerine in-flight/replay.

    return response


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

    provided = (
        request.headers.get("X-IYZ-SIGNATURE")
        or request.headers.get("X-Iyz-Signature")
        or ""
    )
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
    intent = await db.payment_intents.find_one(
        {"conversation_token": conversation_id}, {"_id": 0}
    )
    if not intent:
        # Bize ait olmayan/eski olay: sessizce kabul et (retry firtinasi olmasin).
        return {"status": "ignored"}
    tenant_id = intent["tenant_id"]

    # Olay dedup (idempotent ingest): _id tekilligi.
    event_key = hashlib.sha256(
        f"{tenant_id}:{conversation_id}:{payload.get('paymentId') or ''}:"
        f"{payload.get('iyziEventType') or payload.get('status') or ''}".encode()
    ).hexdigest()
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
        {"$set": {
            "webhook_status": webhook_status,
            "webhook_provider_ref": str(payload.get("paymentId") or "") or None,
            "updated_at": datetime.now(UTC).isoformat(),
        }},
    )
    return {"status": "processed", "intent_status": webhook_status}
