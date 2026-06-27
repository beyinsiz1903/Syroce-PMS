"""Saglayici-bagimsiz tahsilat durum makinesi (tek dogruluk kaynagi).

Operator-tetikli endpoint (``routers/payments_router.py``) ve otonom tahsilat
worker'i (``core/autonomous_collection.py``) ayni cekirdek akisi paylasir:

    claim (idempotency) -> intent(pending) -> PSP charge (transaction DISINDA)
    -> basari: atomik kayit (payment + folio bakiye dec + booking paid_amount inc
       + intent completed + idempotency completion [+ cagirana ozel on_success_ops])
    -> sonuc.

Cift-charge guvenligi YAPISAL:
- PSP cagrisi (harici I/O) Mongo transaction'ina GIREMEZ.
- Basari yalnizca tek atomik blokta kaydedilir; PSP tahsil ettiyse kaydi
  kaybetmemek icin yalnizca replica-set yoksa VE operator acikca izin verdiyse
  (dev standalone) tx'siz best-effort fallback yapilir.
- Sonuc belirsiz (5xx) ise intent 'unknown' kalir ve idempotency kilidi
  BIRAKILMAZ; tekrar denemede cift-charge yerine in-flight/replay olusur.

Bu modul HTTPException ATMAZ; yapisal ``CollectionOutcome`` dondurur. Cagiranlar
sonucu kendi baglamina cevirir: endpoint -> HTTP eslemesi, worker -> operator
kuyrugu + kalici marker. Ham PAN/CVV/secret ASLA loglanmaz; yanit yalnizca
maskeli kart tasir.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
)
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    release_idempotency,
)

from .contracts import (
    PaymentError,
    PaymentOperation,
    PaymentRequest,
    PaymentStatus,
)
from .registry import get_provider_for_tenant

logger = logging.getLogger(__name__)

# on_success_ops imzasi: async def(session, ctx: dict) -> None
OnSuccessOps = Callable[[object, dict], Awaitable[None]]


@dataclass
class CollectionOutcome:
    """Tahsilat denemesinin yapisal sonucu (HTTP'den bagimsiz).

    status degerleri:
      - ``paid``            : tahsilat basarili, kayit atomik yazildi.
      - ``replay``          : ayni idempotency key zaten tamamlandi (cached yanit).
      - ``in_flight``       : ayni key ile baska bir istek isleniyor.
      - ``requires_action`` : 3DS yonlendirmesi gerekli (intent acik kalir).
      - ``failed``          : PSP reddi/4xx hata (kilit birakildi, retry serbest).
      - ``unknown``         : sonuc belirsiz/5xx (kilit TUTULUR, reconcile gerekir).
      - ``not_configured``  : tenant icin aktif/yapilandirilmis saglayici yok.
    """

    status: str
    response: dict | None = None
    intent_id: str | None = None
    requires_action_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    detail: str | None = None
    http_status: int | None = None
    amount_major: float | None = None
    provider_ref: str | None = None
    masked_card: str | None = None
    payment_id: str | None = None


async def collect_booking_payment(
    db_handle,
    *,
    tenant_id: str,
    booking_id: str,
    folio: dict,
    amount_minor: int,
    currency: str,
    vault_ref: str,
    idempotency_key: str,
    scope: str,
    payment_type: str,
    processed_by: str | None,
    descriptor: str | None = None,
    metadata: dict | None = None,
    provider=None,
    intent_extra: dict | None = None,
    on_success_ops: OnSuccessOps | None = None,
) -> CollectionOutcome:
    """Kasa karti uzerinden idempotent kart tahsilati yap (tek dogruluk kaynagi).

    ``provider`` verilmezse tenant'in aktif saglayicisi fail-closed secilir
    (yoksa ``not_configured`` outcome'i; intent OLUSTURULMAZ). ``on_success_ops``
    verilirse basari transaction'ina cagirana ozel yazimlar (or. worker'in kalici
    marker'i + kuyruk success dokumani) ayni atomik blokta dahil edilir.
    """
    amount_major = round(amount_minor / 100.0, 2)

    # Saglayici fail-closed (yoksa/yapilandirilmamissa not_configured -> 503).
    if provider is None:
        try:
            provider = await get_provider_for_tenant(db_handle, tenant_id)
        except PaymentError as pe:
            return CollectionOutcome(
                status="not_configured",
                error_code=pe.error_code,
                detail=pe.error_code,
                http_status=pe.http_status,
            )

    # Idempotency claim (replay/in-flight).
    claim = await claim_idempotency(
        db_handle,
        tenant_id=tenant_id,
        scope=scope,
        idempotency_key=idempotency_key,
    )
    if claim["status"] == "replay":
        return CollectionOutcome(status="replay", response=claim["response"])
    if claim["status"] == "in_flight":
        return CollectionOutcome(
            status="in_flight",
            detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            http_status=409,
        )
    lock_id = claim["lock_id"]

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    intent_id = str(uuid.uuid4())
    # conversation_token: SUNUCU-URETIMI, globally-unique korelasyon kimligi. PSP'ye
    # conversationId olarak BU gonderilir; webhook tenant binding'i bunun uzerinden
    # yapilir. Client-controlled idempotency_key tenant'lar arasi cakisabildiginden
    # ASLA PSP korelasyonu/webhook lookup'i icin kullanilmaz.
    conversation_token = uuid.uuid4().hex
    intent_doc = {
        "id": intent_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "folio_id": folio["id"],
        "idempotency_key": idempotency_key,
        "conversation_token": conversation_token,
        "provider": provider.name,
        "operation": PaymentOperation.CHARGE.value,
        "amount_minor": amount_minor,
        "currency": currency.upper(),
        "status": "pending",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    # Cagirana ozel kalici etiketler (or. worker'in collection_kind'i): worker
    # gun-asimi cift-charge guard'ini bu alanlardan turetir (idempotency replay
    # cache'i 24s TTL'li oldugundan tek basina yetmez).
    if intent_extra:
        for k, v in intent_extra.items():
            intent_doc.setdefault(k, v)
    await db_handle.payment_intents.insert_one(intent_doc)

    pay_req = PaymentRequest(
        operation=PaymentOperation.CHARGE,
        tenant_id=tenant_id,
        currency=currency,
        idempotency_key=conversation_token,
        amount_minor=amount_minor,
        vault_card_ref=vault_ref,
        booking_id=booking_id,
        descriptor=descriptor,
        metadata=dict(metadata or {}),
    )

    # ── PSP cagrisi (transaction DISINDA) ─────────────────────────
    try:
        result = await provider.charge(pay_req)
    except PaymentError as pe:
        # 5xx -> durum belirsiz: intent 'unknown', kilit BIRAKILMAZ (reconcile).
        # 4xx -> kesin hata: intent 'failed', kilit birakilir (retry serbest).
        unknown = pe.http_status >= 500
        await db_handle.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "unknown" if unknown else "failed",
                "error_code": pe.error_code,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        if not unknown:
            await release_idempotency(db_handle, lock_id=lock_id)
        return CollectionOutcome(
            status="unknown" if unknown else "failed",
            intent_id=intent_id,
            error_code=pe.error_code,
            detail=pe.error_code,
            http_status=pe.http_status,
        )
    except Exception:
        # Beklenmeyen: durum belirsiz kabul edilir (cift-charge riski) -> kilit tut.
        await db_handle.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {"status": "unknown", "updated_at": datetime.now(UTC).isoformat()}},
        )
        logger.exception("tahsilat sirasinda beklenmeyen hata (durum belirsiz)")
        return CollectionOutcome(
            status="unknown",
            intent_id=intent_id,
            error_code="indeterminate",
            detail="tahsilat durumu belirsiz",
            http_status=502,
        )

    if result.status == PaymentStatus.REQUIRES_ACTION:
        # 3DS yonlendirmesi gerekli: intent acik kalir, webhook/worker tamamlar.
        await db_handle.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "requires_action",
                "provider_ref": result.provider_ref,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        await release_idempotency(db_handle, lock_id=lock_id)
        return CollectionOutcome(
            status="requires_action",
            intent_id=intent_id,
            requires_action_url=result.requires_action_url,
            provider_ref=result.provider_ref,
        )

    if not result.ok:
        await db_handle.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "failed",
                "error_code": result.error_code,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )
        await release_idempotency(db_handle, lock_id=lock_id)
        return CollectionOutcome(
            status="failed",
            intent_id=intent_id,
            error_code=result.error_code,
            error_message=result.error_message,
            detail=result.error_message or "tahsilat reddedildi",
            http_status=402,
        )

    # ── Basari: sonucu atomik yaz ─────────────────────────────────
    payment_id = str(uuid.uuid4())
    payment_doc = {
        "id": payment_id,
        "tenant_id": tenant_id,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": amount_major,
        "method": "card",
        "payment_type": payment_type,
        "status": "paid",
        "voided": False,
        "reference": result.provider_ref,
        "provider": provider.name,
        "provider_ref": result.provider_ref,
        "provider_txn_ref": result.provider_txn_ref,
        "masked_card": result.masked_card,
        "idempotency_key": idempotency_key,
        "processed_by": processed_by,
        "processed_at": now_iso,
    }
    response = {
        "id": payment_id,
        "status": "paid",
        "amount": amount_major,
        "provider": provider.name,
        "provider_ref": result.provider_ref,
        "masked_card": result.masked_card,
        "intent_id": intent_id,
    }
    success_ctx = {
        "payment_id": payment_id,
        "provider_ref": result.provider_ref,
        "provider_txn_ref": result.provider_txn_ref,
        "intent_id": intent_id,
        "amount_minor": amount_minor,
        "amount_major": amount_major,
        "currency": currency.upper(),
        "masked_card": result.masked_card,
    }

    async def _record(session=None):
        await db_handle.payments.insert_one(dict(payment_doc), session=session)
        await db_handle.folios.update_one(
            {"id": folio["id"], "tenant_id": tenant_id},
            {"$inc": {"balance": -amount_major}},
            session=session,
        )
        await db_handle.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"$inc": {"paid_amount": amount_major}},
            session=session,
        )
        await db_handle.payment_intents.update_one(
            {"id": intent_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "completed",
                "provider_ref": result.provider_ref,
                "payment_id": payment_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
            session=session,
        )
        if on_success_ops is not None:
            await on_success_ops(session, success_ctx)

    try:
        async with await db_handle.client.start_session() as session:
            async with session.start_transaction():
                await _record(session=session)
                await complete_idempotency(
                    db_handle, lock_id=lock_id, response_body=response, session=session
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
                    db_handle, lock_id=lock_id, response_body=response
                )
            except Exception:  # noqa: BLE001
                logger.exception("idempotency complete failed (non-tx fallback)")
            lock_id = None
        else:
            logger.exception(
                "tahsilat kaydi atomik yazilamadi; intent reconcile'a birakildi"
            )
            await db_handle.payment_intents.update_one(
                {"id": intent_id, "tenant_id": tenant_id},
                {"$set": {
                    "status": "completed_unrecorded",
                    "provider_ref": result.provider_ref,
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            # Kilidi birakma: tekrar denenirse cift-charge yerine in-flight/replay.
            # Para PSP tarafinda alindi: cagiran (endpoint) basari yanitini dondurur
            # (#312 davranisi); kayit reconcile'a kalir. Worker bunu operator
            # kuyruguna 'unrecorded' olarak surer ve booking'i charge edilmis sayar.
            return CollectionOutcome(
                status="paid_unrecorded",
                response=response,
                intent_id=intent_id,
                error_code="record_failed",
                detail="tahsilat kaydi yazilamadi",
                provider_ref=result.provider_ref,
                masked_card=result.masked_card,
                amount_major=amount_major,
                payment_id=payment_id,
            )

    return CollectionOutcome(
        status="paid",
        response=response,
        intent_id=intent_id,
        provider_ref=result.provider_ref,
        masked_card=result.masked_card,
        amount_major=amount_major,
        payment_id=payment_id,
    )
