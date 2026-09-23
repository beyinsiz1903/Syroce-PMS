"""
Kasa servisi: ödeme/folio akışı ile kasa vardiyası entegrasyonu.

- record_cash_transaction: ödeme/iade/manuel kasa hareketi yazar.
- get_active_shift: tenant'ın aktif vardiyasını döner (yoksa None).
- ensure_active_shift: aktif vardiya yoksa HTTPException 409 fırlatır.
- get_shift_transactions: vardiyanın işlem listesini döner.

Atlas Free 500-koleksiyon limitine takılmamak için kasa hareketleri
ayrı bir koleksiyonda değil, ilgili `cashier_shifts` dokümanı içinde
`transactions` array'i olarak tutulur. (laundry_orders ile aynı pattern.)

Tasarım notları:
- Tüm method'lar (cash + card + bank + online) array'e eklenir; "Vardiya
  İşlemleri" listesinde hepsi görünür.
- cashier_shifts.cash_in / cash_out yalnızca method='cash' için artırılır
  (kart işlemleri kasa nakdini etkilemez).
- Idempotency: aynı idempotency_key'e sahip işlem varsa $push atılmaz
  (single-update race-safe filter).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

from core.business_date_service import stamp_open_business_date
from core.database import db

logger = logging.getLogger(__name__)


CASH_METHODS = {"cash"}
ALL_METHODS = {"cash", "card", "bank_transfer", "online"}


async def get_active_shift(tenant_id: str) -> dict | None:
    """Tenant'ın açık vardiyasını döner (yoksa None)."""
    return await db.cashier_shifts.find_one(
        {"tenant_id": tenant_id, "status": "open"},
        sort=[("opened_at", -1)],
    )


async def ensure_active_shift(tenant_id: str, method: str) -> dict | None:
    """
    Nakit (cash) işlemler için aktif vardiya zorunludur. Kart/banka için
    vardiya tercihen olmalı ama yoksa engellenmiyor (POS terminal akışı).

    Returns: aktif shift dokümanı veya None (kart için).
    Raises: 409 vardiya yoksa ve method=cash ise.
    """
    shift = await get_active_shift(tenant_id)
    if shift:
        return shift
    if (method or "").lower() in CASH_METHODS:
        raise HTTPException(
            status_code=409,
            detail="Aktif kasa vardiyası yok. Önce 'Vardiya Aç' işlemini yapın.",
        )
    return None


async def get_shift_transactions(tenant_id: str, shift_id: str | None = None) -> list[dict]:
    """Vardiyanın işlem listesini döner (en yeni önce)."""
    query = {"tenant_id": tenant_id}
    if shift_id:
        query["_id"] = shift_id
    else:
        query["status"] = "open"
    shift = await db.cashier_shifts.find_one(query, {"_id": 0, "transactions": 1})
    txns = (shift or {}).get("transactions") or []
    # En yeni önce
    return sorted(txns, key=lambda t: t.get("created_at") or "", reverse=True)


def _event_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


async def reconcile_open_shift_payments(tenant_id: str) -> int:
    """Backfill cash payments missing from the currently open shift.

    Several legacy payment endpoints wrote the financial payment row but did
    not append the corresponding cashier transaction.  That made X/Z reports
    and handover amounts appear as zero.  Reconciliation is idempotent by
    payment id and is run before reading, closing, or handing over a shift.
    """
    shift = await get_active_shift(tenant_id)
    if not shift:
        return 0

    shift_business_date = str(shift.get("business_date") or "")[:10]
    if not shift_business_date:
        marker: dict = {}
        shift_business_date = await stamp_open_business_date(db, tenant_id, marker)
        await db.cashier_shifts.update_one(
            {"_id": shift["_id"], "tenant_id": tenant_id, "status": "open"},
            {"$set": {"business_date": shift_business_date}},
        )

    candidates = await db.payments.find(
        {
            "tenant_id": tenant_id,
            "$or": [
                {"business_date": shift_business_date},
                {"business_date": {"$exists": False}},
                {"business_date": None},
                {"business_date": ""},
            ],
        },
        {"_id": 0},
    ).to_list(10000)

    opened_at = _event_datetime(shift.get("opened_at"))
    existing_keys = {
        str(txn.get("idempotency_key"))
        for txn in (shift.get("transactions") or [])
        if txn.get("idempotency_key")
    }
    recovered = 0
    for payment in candidates:
        payment_id = str(payment.get("id") or "").strip()
        key = f"payment:{payment_id}"
        if not payment_id or key in existing_keys or payment.get("voided"):
            continue
        status = str(payment.get("status") or "paid").lower()
        if status in {"void", "voided", "failed", "cancelled", "rejected"}:
            continue
        method = str(payment.get("method") or payment.get("payment_method") or "").lower()
        if method != "cash":
            continue
        event_at = _event_datetime(
            payment.get("processed_at") or payment.get("created_at") or payment.get("payment_date") or payment.get("date")
        )
        if opened_at and (event_at is None or event_at < opened_at):
            continue

        amount = float(payment.get("amount") or 0)
        is_refund = str(payment.get("payment_type") or "").lower() == "refund" or amount < 0
        if not str(payment.get("business_date") or "").strip():
            await db.payments.update_one(
                {"id": payment_id, "tenant_id": tenant_id},
                {"$set": {"business_date": shift_business_date}},
            )
        txn = await record_cash_transaction(
            tenant_id=tenant_id,
            amount=abs(amount),
            method="cash",
            direction="out" if is_refund else "in",
            description="Kasa ödeme mutabakatı" if not is_refund else "Kasa iade mutabakatı",
            txn_type="refund" if is_refund else "folio_payment",
            ref_type="payment",
            ref_id=payment_id,
            created_by=payment.get("processed_by") or payment.get("created_by"),
            created_by_name=payment.get("processed_by_name") or payment.get("created_by_name"),
            idempotency_key=key,
            require_open_shift=True,
        )
        if txn:
            existing_keys.add(key)
            recovered += 1
    return recovered


async def record_cash_transaction(
    *,
    tenant_id: str,
    amount: float,
    method: str,
    direction: str,  # "in" | "out"
    description: str,
    txn_type: str = "folio_payment",  # folio_payment|paid_out|manual_in|manual_out|refund|bank_deposit
    ref_type: str | None = None,  # folio|booking|payment|manual|bank
    ref_id: str | None = None,
    created_by: str | None = None,
    created_by_name: str | None = None,
    idempotency_key: str | None = None,
    require_open_shift: bool = False,
    currency: str = "TRY",
    fx_rate: float = 1.0,
    original_amount: float | None = None,
    extra: dict | None = None,
) -> dict | None:
    """
    Kasa hareketi yazar (cashier_shifts.transactions array'ine push) ve
    aktif vardiyanın cash_in/cash_out alanını günceller (yalnızca
    method='cash' için).

    require_open_shift=True ise ve method='cash' ise vardiya yoksa
    HTTPException(409) atar.

    Döviz: currency != "TRY" ise original_amount yabancı tutarı, amount
    TL karşılığını (original_amount × fx_rate) temsil eder. cash_in/out
    her zaman TL bazında artar.
    """
    method_l = (method or "").lower()
    direction_l = (direction or "").lower()
    if direction_l not in {"in", "out"}:
        logger.warning(f"record_cash_transaction: invalid direction {direction!r}")
        return None
    if method_l not in ALL_METHODS:
        method_l = method_l or "other"

    amount_f = float(amount or 0)
    if amount_f <= 0:
        return None

    currency_u = (currency or "TRY").upper()
    fx_rate_f = float(fx_rate or 1.0)
    if fx_rate_f <= 0:
        fx_rate_f = 1.0
    original_amount_f = float(original_amount) if original_amount is not None else amount_f

    shift = await get_active_shift(tenant_id)
    if not shift:
        if require_open_shift and method_l in CASH_METHODS:
            raise HTTPException(
                status_code=409,
                detail="Aktif kasa vardiyası yok. Önce 'Vardiya Aç' işlemini yapın.",
            )
        logger.info(f"cashier txn skipped (no open shift) tenant={tenant_id} method={method_l} amount={amount_f} ref={ref_type}:{ref_id}")
        return None

    now = datetime.utcnow()
    txn = {
        "id": str(uuid.uuid4()),
        "amount": amount_f,
        "method": method_l,
        "direction": direction_l,
        "type": txn_type,
        "description": description or "",
        "ref_type": ref_type,
        "ref_id": ref_id,
        "created_at": now.isoformat(),
        "timestamp": now.isoformat(),
        "created_by": created_by,
        "created_by_name": created_by_name,
        "idempotency_key": idempotency_key,
        "currency": currency_u,
        "fx_rate": fx_rate_f,
        "original_amount": original_amount_f,
    }
    await stamp_open_business_date(db, tenant_id, txn)
    if extra and isinstance(extra, dict):
        for k, v in extra.items():
            if k not in txn:
                txn[k] = v

    # Atomik push + cash_in/out increment (idempotency: aynı key varsa hiç
    # push atma; matched_count=0 dönerse zaten kayıtlı demektir)
    update_doc: dict = {"$push": {"transactions": txn}}
    if method_l in CASH_METHODS:
        field = "cash_in" if direction_l == "in" else "cash_out"
        update_doc["$inc"] = {field: amount_f}

    filter_doc: dict = {
        "_id": shift["_id"],
        "tenant_id": tenant_id,
        "status": "open",
    }
    if idempotency_key:
        filter_doc["transactions.idempotency_key"] = {"$ne": idempotency_key}

    try:
        result = await db.cashier_shifts.update_one(filter_doc, update_doc)
    except Exception as e:
        logger.error(f"cashier txn push failed: {e}")
        return None

    if result.matched_count == 0:
        # idempotency engelledi (zaten kayıtlı) veya vardiya artık açık değil
        # Mevcut kaydı bul ve döndür (kullanıcıya aynı sonuç) — idempotent başarı
        if idempotency_key:
            existing_shift = await db.cashier_shifts.find_one(
                {"tenant_id": tenant_id, "transactions.idempotency_key": idempotency_key},
                {"_id": 0, "transactions": 1},
            )
            if existing_shift:
                for t in existing_shift.get("transactions") or []:
                    if t.get("idempotency_key") == idempotency_key:
                        logger.info(f"cashier txn idempotent hit key={idempotency_key}")
                        return t
        # Mevcut kayıt yok → race condition (vardiya bu arada kapandı/devredildi)
        logger.warning(f"cashier txn race: shift no longer open tenant={tenant_id} shift={shift.get('_id')} method={method_l}")
        if require_open_shift and method_l in CASH_METHODS:
            raise HTTPException(
                status_code=409,
                detail="Vardiya işlem sırasında kapandı/devredildi. Tekrar açıp deneyin.",
            )
        return None

    return txn
