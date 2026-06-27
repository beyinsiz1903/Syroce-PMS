"""Otonom tahsilat motoru (no-show cezasi + check-in gunu VCC capture).

Her kiracinin yerel gun donumunde celery dispatcher tetikler. Iki tahsilat turu:

- ``vcc_checkin`` : bugun check-in olan, kasa karti (VCC) bulunan ve acik guest
  folyo bakiyesi > 0 rezervasyonlarda kart capture (acik bakiye kadar).
- ``no_show``     : night-audit'in ``no_show``'a cektigi, kasa karti bulunan ve
  ``cancellation_policy.no_show_fee`` > 0 rezervasyonlarda ceza tahsilati.

Cift-charge guvenligi (MUTLAK):
- Tahsilat cekirdegi tek dogruluk kaynagi: ``core.payments.collection
  .collect_booking_payment`` (PSP tx-disi, basari atomik, belirsizde kilit tutulur).
- Kalici "tahsil edildi" isareti booking uzerinde set edilir (TTL YOK). Idempotency
  replay cache'i ``IDEMPOTENCY_RETENTION_SECONDS`` (24s) TTL'li oldugundan TEK
  BASINA "sonsuza dek bir kez" SAGLAMAZ; borc gun asimiyla yeniden taranirsa cift-
  charge olusabilirdi. Kalici booking marker + para-alinmis-olabilir intent guard'i
  bunu kapatir.
- Basarisizlik operator-gorunur kuyruga (``autonomous_collection_jobs``) yazilir;
  sahte basari ASLA yazilmaz. Saglayici yapilandirilmamissa fail-closed: kuyruga
  ``not_configured`` (charge denenmez).
- 3DS gereken (``requires_action``) tahsilatlar otonom tamamlanamaz; operator
  kuyruguna surulur, booking marker SET EDILMEZ.
- Tarihsel backfill yok: ``no_show`` adaylari yakin tarih penceresiyle sinirlidir
  (eski no-show'lar otomatik tahsil edilmez).
- PII/secret/PAN loglanmaz; yalnizca booking_id + maskeli kart + hata kodu kalir.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pymongo import ReturnDocument

from core.payments import PaymentError, get_provider_for_tenant, make_vault_card_ref
from core.payments.collection import collect_booking_payment
from models.enums import PaymentType

logger = logging.getLogger(__name__)

CHARGE_KIND_VCC_CHECKIN = "vcc_checkin"
CHARGE_KIND_NO_SHOW = "no_show"
# Check-in gunu VCC capture'a uygun rezervasyon durumlari.
VCC_CHECKIN_STATUSES = ["confirmed", "guaranteed", "checked_in"]
# Para-alinmis-olabilir intent durumlari: bu booking+kind icin boyle bir intent
# varsa ASLA tekrar charge edilmez (gun-asimi cift-charge guard'i).
_MONEY_TAKEN_INTENT_STATES = [
    "pending",
    "requires_action",
    "unknown",
    "completed",
    "completed_unrecorded",
]


def _max_attempts() -> int:
    try:
        return max(1, int(os.getenv("AUTOCOLLECT_MAX_ATTEMPTS", "3")))
    except (TypeError, ValueError):
        return 3


def _no_show_lookback_days() -> int:
    try:
        return max(0, int(os.getenv("AUTOCOLLECT_NO_SHOW_LOOKBACK_DAYS", "3")))
    except (TypeError, ValueError):
        return 3


def _to_minor(amount) -> int:
    """Major (TL) tutari kurus-tam integer'e cevir (Decimal, float aritmetigi yok)."""
    q = (Decimal(str(amount or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(q)


def _marker_field(kind: str) -> str:
    return f"autocollect_{kind}_done"


def _sanitize_error(msg) -> str | None:
    """PSP hata mesajini kuyruga yazmadan once sinirla (PII/PAN tasimaz, yine trunc)."""
    if not msg:
        return None
    return str(msg)[:200]


def _date_minus(iso_date: str, days: int) -> str:
    try:
        return (date.fromisoformat(iso_date) - timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return iso_date


async def _resolve_business_date(db, tenant_id: str, business_date: str | None) -> str:
    if business_date:
        return business_date
    ts = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "business_date": 1}
    )
    return (ts or {}).get("business_date") or datetime.now(UTC).date().isoformat()


async def _ensure_indexes(db) -> None:
    try:
        await db.autonomous_collection_jobs.create_index(
            [("tenant_id", 1), ("booking_id", 1), ("charge_kind", 1)],
            unique=True,
            name="autocollect_jobs_uq",
            background=True,
        )
    except Exception as e:  # noqa: BLE001 — index bir optimizasyon/backstop, zorunlu degil
        logger.debug("[autocollect] job index ensure skipped: %s", e)


# ─────────────────────────── candidate selection ───────────────────────────


async def _posted_no_show_fee(db, tenant_id: str, folio_id: str, booking_id: str) -> float:
    """Folyoya GERCEKTEN islenmis, void edilmemis no-show ucretinin toplami.

    Night-audit no_show_fee'yi ``folio_charges`` (charge_category=no_show_fee)
    olarak isler; void edilen ucret ``voided=True`` olur. Bu toplam, otonom
    tahsilatin POLITIKA ucretine degil islenmis alacaga baglanmasini saglar.
    """
    total = 0.0
    cur = db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "charge_category": "no_show_fee",
            "voided": {"$ne": True},
        },
        {"_id": 0, "amount": 1, "total": 1},
    )
    async for ch in cur:
        total += float(ch.get("total") or ch.get("amount") or 0)
    return total


async def _build_candidate(db, tenant_id: str, booking: dict, kind: str) -> dict | None:
    booking_id = booking["id"]
    card = await db.vcc_cards.find_one(
        {"booking_id": booking_id, "tenant_id": tenant_id}, {"_id": 0, "id": 1}
    )
    if not card:
        # Kasa karti yok -> otonom tahsilat yapilamaz (manuel surece birakilir).
        return None

    folio = await db.folios.find_one(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "folio_type": "guest",
            "status": "open",
        },
        {"_id": 0},
    )

    if kind == CHARGE_KIND_VCC_CHECKIN:
        if not folio:
            return None
        amount_minor = _to_minor(folio.get("balance", 0))
        if amount_minor <= 0:
            return None
    else:  # no_show
        # Otonom no-show tahsilati POLITIKA ucretine DEGIL, gercek acik borca
        # baglanir: tahsil edilecek tutar = min(folyoya islenmis no-show ucreti,
        # acik folyo bakiyesi). Boylece operatorun manuel tahsilati, kismi
        # odeme, indirim veya ucretin void edilmesi sonrasi otonom worker ASLA
        # cift-charge etmez (cross-path duplicate guard: acik bakiye tek dogruluk
        # kaynagidir, sadece collection_kind intent marker'i degil).
        if not folio:
            return None  # acik guest folyo yok -> tahsil edilecek acik borc yok
        posted_fee = await _posted_no_show_fee(db, tenant_id, folio["id"], booking_id)
        if posted_fee <= 0:
            return None  # night-audit ucreti islememis ya da void edilmis -> skip
        outstanding = folio.get("balance", 0) or 0
        amount_minor = _to_minor(min(posted_fee, outstanding))
        if amount_minor <= 0:
            return None  # borc zaten kapatilmis (manuel tahsilat / indirim) -> skip

    currency = (
        booking.get("currency")
        or (folio.get("currency") if folio else None)
        or "TRY"
    )
    return {
        "kind": kind,
        "booking_id": booking_id,
        "folio": folio,
        "vault_ref": make_vault_card_ref(card["id"]),
        "amount_minor": amount_minor,
        "currency": currency,
    }


async def _gather_candidates(db, tenant_id: str, bd: str) -> list[dict]:
    candidates: list[dict] = []

    # VCC check-in: yalnizca bugun check-in olanlar (backfill riski yok).
    vcc_marker = _marker_field(CHARGE_KIND_VCC_CHECKIN)
    cur = db.bookings.find(
        {
            "tenant_id": tenant_id,
            "check_in": bd,
            "status": {"$in": VCC_CHECKIN_STATUSES},
            vcc_marker: {"$ne": True},
        },
        {"_id": 0, "id": 1, "currency": 1},
    )
    async for b in cur:
        cand = await _build_candidate(db, tenant_id, b, CHARGE_KIND_VCC_CHECKIN)
        if cand:
            candidates.append(cand)

    # No-show: yakin tarih penceresi (eski no-show'lari otomatik tahsil etme).
    ns_marker = _marker_field(CHARGE_KIND_NO_SHOW)
    cutoff = _date_minus(bd, _no_show_lookback_days())
    cur2 = db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "check_in": {"$gte": cutoff},
            ns_marker: {"$ne": True},
        },
        {"_id": 0, "id": 1, "currency": 1, "cancellation_policy": 1},
    )
    async for b in cur2:
        cand = await _build_candidate(db, tenant_id, b, CHARGE_KIND_NO_SHOW)
        if cand:
            candidates.append(cand)

    return candidates


# ─────────────────────────── persistence helpers ───────────────────────────


async def _mark_booking_done(
    db, tenant_id: str, booking_id: str, kind: str, status: str,
    *, payment_id: str | None = None, session=None,
) -> None:
    now_iso = datetime.now(UTC).isoformat()
    setd = {
        _marker_field(kind): True,
        f"autocollect_{kind}_status": status,
        f"autocollect_{kind}_at": now_iso,
    }
    if payment_id:
        setd[f"autocollect_{kind}_payment_id"] = payment_id
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id}, {"$set": setd}, session=session
    )


async def _upsert_job(
    db, tenant_id: str, cand: dict, fields: dict,
    *, inc_attempts: bool = False, session=None,
) -> dict:
    now_iso = datetime.now(UTC).isoformat()
    update = {
        "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": cand["booking_id"],
            "charge_kind": cand["kind"],
            "created_at": now_iso,
        },
        "$set": {
            "amount_minor": cand["amount_minor"],
            "currency": cand["currency"],
            "updated_at": now_iso,
            **fields,
        },
    }
    if inc_attempts:
        update["$inc"] = {"attempts": 1}
    res = await db.autonomous_collection_jobs.find_one_and_update(
        {
            "tenant_id": tenant_id,
            "booking_id": cand["booking_id"],
            "charge_kind": cand["kind"],
        },
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    return res or {}


# ─────────────────────────── per-candidate processing ───────────────────────


async def _process_candidate(db, tenant_id: str, provider, cand: dict, summary: dict) -> None:
    kind = cand["kind"]
    booking_id = cand["booking_id"]
    scope = f"autocollect:{kind}"
    idem_key = booking_id  # deterministik: (tenant, scope, key) -> stabil lock_id

    # Kalici cift-charge guard: bu booking+kind icin para-alinmis-olabilir bir intent
    # zaten varsa ASLA tekrar charge etme (24s idempotency TTL'inden bagimsiz).
    guard = await db.payment_intents.find_one(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "collection_kind": kind,
            "status": {"$in": _MONEY_TAKEN_INTENT_STATES},
        },
        {"_id": 0, "status": 1, "payment_id": 1},
    )
    if guard:
        st = guard.get("status")
        if st == "completed":
            # Temiz basari (marker yazimi eski surumde kacmis olabilir): self-heal.
            await _mark_booking_done(db, tenant_id, booking_id, kind, "collected",
                                     payment_id=guard.get("payment_id"))
            await _upsert_job(db, tenant_id, cand, {
                "status": "succeeded", "resolved": True,
                "payment_id": guard.get("payment_id"),
                "last_error_code": None, "last_error_message": None,
            })
        else:
            # pending / requires_action / unknown / completed_unrecorded -> reconcile.
            await _upsert_job(db, tenant_id, cand, {
                "status": "reconcile", "resolved": False,
                "last_error_code": st, "last_error_message": None,
            })
        summary["skipped"] += 1
        return

    payment_type = (
        PaymentType.PREPAYMENT.value
        if kind == CHARGE_KIND_VCC_CHECKIN
        else PaymentType.FINAL.value
    )

    async def _on_success(session, ctx):
        await _mark_booking_done(
            db, tenant_id, booking_id, kind, "collected",
            payment_id=ctx["payment_id"], session=session,
        )
        await _upsert_job(db, tenant_id, cand, {
            "status": "succeeded", "resolved": True,
            "payment_id": ctx["payment_id"], "provider_ref": ctx["provider_ref"],
            "last_error_code": None, "last_error_message": None,
        }, session=session)

    outcome = await collect_booking_payment(
        db,
        tenant_id=tenant_id,
        booking_id=booking_id,
        folio=cand["folio"],
        amount_minor=cand["amount_minor"],
        currency=cand["currency"],
        vault_ref=cand["vault_ref"],
        idempotency_key=idem_key,
        scope=scope,
        payment_type=payment_type,
        processed_by="system:autonomous_collection",
        descriptor=f"autocollect:{kind}",
        metadata={"collection_kind": kind},
        provider=provider,
        intent_extra={"collection_kind": kind, "source": "autonomous_collection"},
        on_success_ops=_on_success,
    )

    await _apply_outcome(db, tenant_id, cand, outcome, summary)


async def _apply_outcome(db, tenant_id: str, cand: dict, outcome, summary: dict) -> None:
    kind = cand["kind"]
    booking_id = cand["booking_id"]
    st = outcome.status

    if st == "paid":
        # marker + job zaten on_success_ops icinde atomik yazildi.
        summary["charged"] += 1
        return

    if st == "replay":
        # 24s icinde zaten tahsil edildi; marker'in kurulu oldugundan emin ol.
        await _mark_booking_done(db, tenant_id, booking_id, kind, "collected")
        summary["charged"] += 1
        return

    if st == "in_flight":
        summary["skipped"] += 1
        return

    if st == "requires_action":
        # 3DS otonom tamamlanamaz: operator kuyruguna sur, marker SET ETME.
        await _upsert_job(db, tenant_id, cand, {
            "status": "requires_action", "resolved": False,
            "last_error_code": "requires_action", "last_error_message": None,
        })
        summary["requires_action"] += 1
        return

    if st == "paid_unrecorded":
        # Para alindi, kayit yazilamadi -> booking'i charge edilmis say (re-charge YOK),
        # operator kuyruguna 'unrecorded' olarak sur (reconcile gerekir).
        await _mark_booking_done(db, tenant_id, booking_id, kind, "unrecorded",
                                 payment_id=outcome.payment_id)
        await _upsert_job(db, tenant_id, cand, {
            "status": "unrecorded", "resolved": False,
            "payment_id": outcome.payment_id, "provider_ref": outcome.provider_ref,
            "last_error_code": "record_failed", "last_error_message": None,
        })
        summary["unrecorded"] += 1
        return

    # failed / unknown / not_configured -> operator kuyruguna (sahte basari YOK).
    job = await _upsert_job(db, tenant_id, cand, {
        "status": st, "resolved": False,
        "last_error_code": outcome.error_code,
        "last_error_message": _sanitize_error(outcome.error_message),
    }, inc_attempts=True)
    if int(job.get("attempts", 1)) >= _max_attempts():
        # Otomatik deneme spam'lemesin: marker=abandoned (scan'den dusur); job
        # operator icin acik kalir.
        await _mark_booking_done(db, tenant_id, booking_id, kind, "abandoned")
    summary["failed"] += 1


# ───────────────────────────────── engine ──────────────────────────────────


async def run_autonomous_collection(
    db, tenant_id: str, *, business_date: str | None = None,
) -> dict:
    """Bir kiraci icin otonom tahsilat dongusunu kosar (idempotent, fail-closed).

    Iki tahsilat turunu (vcc_checkin + no_show) tarar, tek dogruluk kaynagi
    cekirdek uzerinden tahsil eder ve sonucu kalici marker + operator kuyruguna
    yazar. PSP cagrisi disinda HER SEY kiraci-bazli filtrelidir (tenant izolasyonu).
    """
    bd = await _resolve_business_date(db, tenant_id, business_date)
    summary = {
        "tenant_id": tenant_id, "business_date": bd, "scanned": 0,
        "charged": 0, "failed": 0, "skipped": 0,
        "requires_action": 0, "unrecorded": 0, "not_configured": 0,
    }

    await _ensure_indexes(db)
    candidates = await _gather_candidates(db, tenant_id, bd)
    summary["scanned"] = len(candidates)
    if not candidates:
        return summary

    # Saglayici bir kez cozulur (fail-closed). Yapilandirilmamissa charge DENENMEZ;
    # adaylar operator-gorunur kuyruga not_configured olarak surulur (sahte basari YOK).
    try:
        provider = await get_provider_for_tenant(db, tenant_id)
    except PaymentError as pe:
        for cand in candidates:
            await _upsert_job(db, tenant_id, cand, {
                "status": "not_configured", "resolved": False,
                "last_error_code": pe.error_code, "last_error_message": None,
            }, inc_attempts=True)
            summary["not_configured"] += 1
        return summary

    for cand in candidates:
        await _process_candidate(db, tenant_id, provider, cand, summary)

    return summary
