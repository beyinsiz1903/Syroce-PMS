"""Currency-safe credit-limit admission checks for agency reservations."""

from __future__ import annotations

import math

from fastapi import HTTPException


def _currency(value: object) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise HTTPException(409, "Kredi limiti için geçerli üç harfli para birimi gerekli")
    return code


def _money(value: object, field: str) -> float:
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, f"Kredi hesabındaki {field} değeri geçersiz; kayıt incelenmelidir") from exc
    if not math.isfinite(amount) or amount < 0:
        raise HTTPException(409, f"Kredi hesabındaki {field} değeri geçersiz; kayıt incelenmelidir")
    return amount


def booking_net_exposure(booking: dict) -> float:
    """Return the hotel's deterministic net receivable for one booking.

    The platform fee belongs to the agency/platform relationship and never
    reduces the hotel's credit exposure.  Older rows can be reconstructed only
    where their persisted gross amount and agency commission are both present.
    """
    if booking.get("credit_exposure_amount") is not None:
        return _money(booking["credit_exposure_amount"], "net kredi tutarı")
    if booking.get("net_to_hotel") is not None:
        return _money(booking["net_to_hotel"], "net otel alacağı")
    if booking.get("total_amount") is not None and booking.get("agency_commission_amount") is not None:
        total = _money(booking["total_amount"], "brüt rezervasyon tutarı")
        commission = _money(booking["agency_commission_amount"], "acente komisyonu")
        if commission > total:
            raise HTTPException(409, "Kredi hesabındaki acente komisyonu brüt tutarı aşıyor; kayıt incelenmelidir")
        return round(total - commission, 2)
    raise HTTPException(409, "Geçmiş rezervasyonun net kredi tutarı eksik; kayıt düzeltilmeden yeni satış yapılamaz")


async def assert_credit_capacity(
    database,
    *,
    tenant_id: str,
    agency_id: str,
    contract: dict,
    booking_currency: str,
    new_net_exposure: float,
    exclude_booking_id: str | None = None,
) -> None:
    """Reject mixed-currency or over-limit agency sales without FX guessing."""
    limit = contract.get("credit_limit")
    if limit is None:
        return
    limit_amount = _money(limit, "sözleşme kredi limiti")
    credit_currency = _currency(contract.get("credit_currency"))
    sale_currency = _currency(booking_currency)
    if sale_currency != credit_currency:
        raise HTTPException(
            409,
            f"Rezervasyon para birimi ({sale_currency}) sözleşme kredi para biriminden ({credit_currency}) farklı. Kur tanımı olmadan satış yapılamaz.",
        )
    new_exposure = _money(new_net_exposure, "yeni rezervasyon net tutarı")
    query = {
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "status": {"$ne": "cancelled"},
        "payment_status": {"$ne": "paid"},
    }
    if exclude_booking_id:
        query["id"] = {"$ne": exclude_booking_id}
    rows = await database.bookings.find(
        query,
        {"_id": 0, "currency": 1, "credit_exposure_currency": 1, "credit_exposure_amount": 1,
         "net_to_hotel": 1, "total_amount": 1, "agency_commission_amount": 1},
    ).to_list(None)
    debt = 0.0
    for row in rows:
        row_currency = _currency(row.get("credit_exposure_currency") or row.get("currency"))
        if row_currency != credit_currency:
            raise HTTPException(
                409,
                f"Açık borçlarda {row_currency} para birimi var; {credit_currency} kredi limitiyle kur dönüşümü olmadan birlikte hesaplanamaz.",
            )
        debt = round(debt + booking_net_exposure(row), 2)
    if round(debt + new_exposure, 2) > limit_amount:
        raise HTTPException(409, "Acente kredi limiti bu rezervasyon için yetersiz")
