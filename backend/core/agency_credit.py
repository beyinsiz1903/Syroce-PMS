"""Currency-safe credit-limit admission checks for agency reservations."""

from __future__ import annotations

import math

from fastapi import HTTPException

from core.booking_payment_state import collected_amount


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
    statements_db=None,
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
        {"_id": 0, "id": 1, "currency": 1, "credit_exposure_currency": 1, "credit_exposure_amount": 1,
         "net_to_hotel": 1, "total_amount": 1, "agency_commission_amount": 1},
    ).to_list(None)
    ids = [row.get("id") for row in rows] + [exclude_booking_id]
    settled = await _settled_through_statements(statements_db, tenant_id, agency_id, ids)
    collected = await _collected_by_booking(database, tenant_id, ids)
    if exclude_booking_id:
        # A modified booking replaces its old exposure, but what was already
        # paid for it (statement or PMS collection) still counts.
        new_exposure = round(max(0.0, new_exposure - _paid_towards(settled.get(exclude_booking_id), collected.get(exclude_booking_id))), 2)
    debt = 0.0
    for row in rows:
        row_currency = _currency(row.get("credit_exposure_currency") or row.get("currency"))
        if row_currency != credit_currency:
            raise HTTPException(
                409,
                f"Açık borçlarda {row_currency} para birimi var; {credit_currency} kredi limitiyle kur dönüşümü olmadan birlikte hesaplanamaz.",
            )
        remaining = max(0.0, booking_net_exposure(row) - _paid_towards(settled.get(row.get("id")), collected.get(row.get("id"))))
        debt = round(debt + remaining, 2)
    if round(debt + new_exposure, 2) > limit_amount:
        raise HTTPException(409, "Acente kredi limiti bu rezervasyon için yetersiz")


def _paid_towards(statement_settled: float | None, collected: float | None) -> float:
    """What is already paid on a booking's net exposure.

    Statement payments and PMS collections (guest or agency payments posted
    on the reservation) can describe the same money, so the larger of the
    two counts, never their sum.
    """
    return max(float(statement_settled or 0.0), float(collected or 0.0))


async def _collected_by_booking(database, tenant_id: str, booking_ids: list) -> dict[str, float]:
    ids = [booking_id for booking_id in booking_ids if booking_id]
    if not ids:
        return {}
    rows = await database.payments.find(
        {"tenant_id": tenant_id, "booking_id": {"$in": ids}},
        {"_id": 0, "booking_id": 1, "amount": 1, "method": 1, "payment_type": 1, "status": 1, "voided": 1},
    ).to_list(None)
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.get("booking_id"), []).append(row)
    return {booking_id: collected_amount(items) for booking_id, items in grouped.items()}


async def _settled_through_statements(statements_db, tenant_id: str, agency_id: str, booking_ids: list) -> dict[str, float]:
    """Debt already paid through period statements (the single finance source)."""
    ids = [booking_id for booking_id in booking_ids if booking_id]
    if not ids:
        return {}
    from core.agency_statements import settled_by_booking

    if statements_db is None:
        from core.tenant_db import get_system_db

        statements_db = get_system_db()
    statements = await statements_db.agency_statements.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "status": {"$ne": "void"}, "lines.booking_id": {"$in": ids}},
        {"_id": 0, "status": 1, "totals": 1, "payments": 1, "lines.booking_id": 1, "lines.agency_owes_hotel": 1},
    ).to_list(None)
    settled: dict[str, float] = {}
    for statement in statements:
        for booking_id, amount in settled_by_booking(statement).items():
            settled[booking_id] = round(settled.get(booking_id, 0.0) + amount, 2)
    return settled
