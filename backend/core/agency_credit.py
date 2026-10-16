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
    debt, paid_on_excluded = await open_credit_exposure(
        database, tenant_id=tenant_id, agency_id=agency_id, credit_currency=credit_currency,
        exclude_booking_id=exclude_booking_id, statements_db=statements_db,
    )
    if exclude_booking_id:
        # A modified booking replaces its old exposure, but what was already
        # paid for it (statement or PMS collection) still counts.
        new_exposure = round(max(0.0, new_exposure - paid_on_excluded), 2)
    if round(debt + new_exposure, 2) > limit_amount:
        raise HTTPException(409, "Acente kredi limiti bu rezervasyon için yetersiz")


async def open_credit_exposure(
    database, *, tenant_id: str, agency_id: str, credit_currency: str,
    exclude_booking_id: str | None = None, statements_db=None,
) -> tuple[float, float]:
    """Open net debt of an agency at one hotel, after statement payments and
    PMS collections; plus what is already paid on ``exclude_booking_id``."""
    query = {
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "status": {"$ne": "cancelled"},
        "payment_status": {"$ne": "paid"},
    }
    # A booking paid in the PMS, or cancelled, can still owe a statement
    # charge (hotel surcharge, cancellation penalty): read it as well.
    statement_debtors = await _statement_debtor_ids(statements_db, tenant_id, agency_id)
    if statement_debtors:
        query = {"tenant_id": tenant_id, "agency_id": agency_id,
                 "$or": [{"status": {"$ne": "cancelled"}, "payment_status": {"$ne": "paid"}},
                         {"id": {"$in": statement_debtors}}]}
    if exclude_booking_id:
        query["id"] = {"$ne": exclude_booking_id}
    rows = await database.bookings.find(
        query,
        {"_id": 0, "id": 1, "status": 1, "currency": 1, "credit_exposure_currency": 1, "credit_exposure_amount": 1,
         "net_to_hotel": 1, "total_amount": 1, "agency_commission_amount": 1},
    ).to_list(None)
    ids = [row.get("id") for row in rows] + [exclude_booking_id]
    settled, adjusted, statement_owed = await _settled_through_statements(statements_db, tenant_id, agency_id, ids)
    collected = await _collected_by_booking(database, tenant_id, ids)
    debt = 0.0
    for row in rows:
        row_currency = _currency(row.get("credit_exposure_currency") or row.get("currency"))
        if row_currency != credit_currency:
            raise HTTPException(
                409,
                f"Açık borçlarda {row_currency} para birimi var; {credit_currency} kredi limitiyle kur dönüşümü olmadan birlikte hesaplanamaz.",
            )
        if row.get("status") == "cancelled":
            # No stay to pay for: only what its statement lines charge
            # (penalty and/or the hotel's surcharge).
            owed = statement_owed.get(row.get("id"), 0.0)
        else:
            owed = booking_net_exposure(row) + adjusted.get(row.get("id"), 0.0)
        remaining = max(0.0, owed - _paid_towards(settled.get(row.get("id")), collected.get(row.get("id"))))
        debt = round(debt + remaining, 2)
    # A correction on the modified booking still applies to its new amount.
    paid_on_excluded = (round(_paid_towards(settled.get(exclude_booking_id), collected.get(exclude_booking_id))
                              - adjusted.get(exclude_booking_id, 0.0), 2) if exclude_booking_id else 0.0)
    return debt, paid_on_excluded


async def credit_usage(database, *, tenant_id: str, agency_id: str, contract: dict, statements_db=None) -> dict | None:
    """Limit, used and available credit for one contract (None: no limit)."""
    if contract.get("credit_limit") is None:
        return None
    limit_amount = _money(contract["credit_limit"], "sözleşme kredi limiti")
    currency = _currency(contract.get("credit_currency"))
    used, _ = await open_credit_exposure(database, tenant_id=tenant_id, agency_id=agency_id,
                                         credit_currency=currency, statements_db=statements_db)
    return {"limit": limit_amount, "used": used, "available": round(max(0.0, limit_amount - used), 2), "currency": currency}


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


async def _statement_debtor_ids(statements_db, tenant_id: str, agency_id: str) -> list[str]:
    """Bookings a statement charges beyond their stay: a positive (agency
    owes more) correction, or a cancelled / no-show line the agency owes."""
    if statements_db is None:
        from core.tenant_db import get_system_db

        statements_db = get_system_db()
    rows = await statements_db.agency_statements.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "status": {"$ne": "void"},
         "$or": [{"lines.adjustment.amount": {"$gt": 0}},
                 {"lines": {"$elemMatch": {"status": {"$in": ["cancelled", "no_show"]}, "agency_owes_hotel": {"$gt": 0}}}}]},
        {"_id": 0, "lines.booking_id": 1, "lines.status": 1, "lines.agency_owes_hotel": 1, "lines.adjustment.amount": 1},
    ).to_list(None)
    ids = set()
    for row in rows:
        for line in row.get("lines") or []:
            surcharge = float((line.get("adjustment") or {}).get("amount") or 0) > 0
            penalty = line.get("status") in ("cancelled", "no_show") and float(line.get("agency_owes_hotel") or 0) > 0
            if line.get("booking_id") and (surcharge or penalty):
                ids.add(line["booking_id"])
    return sorted(ids)


async def _settled_through_statements(statements_db, tenant_id: str, agency_id: str, booking_ids: list) -> tuple[dict, dict, dict]:
    """Per booking: debt already paid through period statements (the single
    finance source); the hotel's signed line corrections (- the agency owes
    less, + more); and what the statement lines charge in total."""
    ids = [booking_id for booking_id in booking_ids if booking_id]
    if not ids:
        return {}, {}, {}
    from core.agency_statements import settled_by_booking

    if statements_db is None:
        from core.tenant_db import get_system_db

        statements_db = get_system_db()
    statements = await statements_db.agency_statements.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "status": {"$ne": "void"}, "lines.booking_id": {"$in": ids}},
        {"_id": 0, "status": 1, "totals": 1, "payments": 1, "lines.booking_id": 1, "lines.agency_owes_hotel": 1,
         "lines.adjustment.amount": 1},
    ).to_list(None)
    settled: dict[str, float] = {}
    adjusted: dict[str, float] = {}
    owed: dict[str, float] = {}
    for statement in statements:
        for booking_id, amount in settled_by_booking(statement).items():
            settled[booking_id] = round(settled.get(booking_id, 0.0) + amount, 2)
        for line in statement.get("lines") or []:
            if line.get("booking_id"):
                owed[line["booking_id"]] = round(owed.get(line["booking_id"], 0.0) + float(line.get("agency_owes_hotel") or 0), 2)
            amount = float((line.get("adjustment") or {}).get("amount") or 0)
            if line.get("booking_id") and abs(amount) >= 0.01:
                adjusted[line["booking_id"]] = round(adjusted.get(line["booking_id"], 0.0) + amount, 2)
    return settled, adjusted, owed
