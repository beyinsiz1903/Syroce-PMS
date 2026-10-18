"""Currency-preserving report arithmetic. No live FX or implicit conversion."""

from decimal import ROUND_HALF_UP, Decimal


def currency_code(value, fallback="TRY") -> str:
    code = str(value or fallback).strip().upper() or fallback
    return "TRY" if code == "TL" else code


def money(value) -> Decimal:
    if type(value).__name__ == "Decimal128":
        value = value.to_decimal()
    amount = Decimal(str(value if value is not None else 0))
    if not amount.is_finite():
        raise ValueError("Report amount must be finite")
    return amount


def rounded(value) -> float:
    return float(money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def add_amount(totals: dict, currency, value) -> None:
    code = currency_code(currency)
    totals[code] = money(totals.get(code, 0)) + money(value)


def rounded_totals(totals: dict) -> dict[str, float]:
    return {code: rounded(amount) for code, amount in sorted(totals.items())}


def single_amount(totals: dict) -> float | None:
    values = [amount for amount in rounded_totals(totals).values() if amount != 0]
    return values[0] if len(values) == 1 else (None if values else 0.0)


def amounts_text(totals: dict) -> str:
    return " · ".join(f"{code} {amount:,.2f}" for code, amount in rounded_totals(totals).items()) or "0.00"


async def resolve_ledger_currencies(rows: list[dict], tenant_id: str, *, database, fallback_currency: str | None = None) -> list[dict]:
    """One currency provenance rule for cash, revenue, Flash and EOD reports."""
    missing = [row for row in rows if not row.get("currency")]
    if not missing:
        return [{**row, "currency": currency_code(row.get("currency"))} for row in rows]
    folio_ids = {str(row["folio_id"]) for row in missing if row.get("folio_id")}
    folios = await database.folios.find({"tenant_id": tenant_id, "id": {"$in": sorted(folio_ids)}},
        {"_id": 0, "id": 1, "booking_id": 1, "currency": 1}).to_list(None) if folio_ids else []
    folio_map = {str(row["id"]): row for row in folios if row.get("id")}
    booking_ids = {str(row["booking_id"]) for row in [*missing, *folios] if row.get("booking_id")}
    bookings = await database.bookings.find({"tenant_id": tenant_id, "id": {"$in": sorted(booking_ids)}},
        {"_id": 0, "id": 1, "currency": 1}).to_list(None) if booking_ids else []
    booking_map = {str(row["id"]): row for row in bookings if row.get("id")}
    result = []
    for row in rows:
        folio = folio_map.get(str(row.get("folio_id"))) or {}
        booking = booking_map.get(str(row.get("booking_id") or folio.get("booking_id"))) or {}
        code = row.get("currency") or folio.get("currency") or booking.get("currency")
        if not code:
            if fallback_currency is None:
                from core.tenant_currency import get_tenant_currency

                fallback_currency, _ = await get_tenant_currency(tenant_id)
            code = fallback_currency
        result.append({**row, "currency": currency_code(code)})
    return result
