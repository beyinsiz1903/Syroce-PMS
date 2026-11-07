"""Immutable service-currency -> folio-currency pricing, without an FX provider."""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException


def laundry_currency(value, default="TRY"):
    value = default if value is None else value
    if not isinstance(value, str):
        raise HTTPException(400, "Para birimi geçersiz")
    code = value.strip().upper()
    code = "TRY" if code == "TL" else code
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise HTTPException(400, "Üç harfli para birimi kodu gereklidir")
    return code


def _positive(value, label):
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= Decimal("1e9"):
            raise ValueError
        return amount
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(400, f"{label} sonlu ve sıfırdan büyük olmalıdır") from exc


def laundry_money_snapshot(total, input_currency, folio_currency, exchange_rate=None):
    source = laundry_currency(input_currency)
    target = laundry_currency(folio_currency)
    amount = _positive(total, "Hizmet toplamı")
    if amount != amount.quantize(Decimal("0.01")):
        raise HTTPException(400, "Hizmet toplamı en fazla iki ondalık olmalıdır")
    # As in the PMS extra-charge form: target units per ONE source unit.
    rate = Decimal("1") if source == target else _positive(exchange_rate, "Farklı para birimi için kur")
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    _positive(converted, "Folyoya yazılacak tutar")
    return {"entered_total": float(amount), "entered_currency": source, "exchange_rate": float(rate),
            "folio_total": float(converted), "folio_currency": target}


def laundry_delivery_money(order, target_currency):
    """Never reinterpret a persisted source after a folio or rate changes."""
    source = laundry_currency(order.get("currency"))
    target = laundry_currency(target_currency)
    if "folio_currency" not in order and source != target:
        raise HTTPException(409, "Eski sipariş için doğrulanmış döviz kuru yok; mali kaydı inceleyin")
    snapshot = laundry_money_snapshot(order.get("total"), source, target, order.get("exchange_rate"))
    try:
        mismatch = "folio_currency" in order and (
            laundry_currency(order["folio_currency"]) != target
            or Decimal(str(order.get("folio_total"))) != Decimal(str(snapshot["folio_total"]))
        )
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(409, "Siparişin kayıtlı döviz tutarı doğrulanamadı") from exc
    if mismatch:
        raise HTTPException(409, "Siparişin kayıtlı kur ve folyo para birimi değişmiş; kaynak incelemesi gerekir")
    return snapshot
