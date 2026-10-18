"""Currency-preserving report arithmetic. No live FX or implicit conversion."""

from decimal import ROUND_HALF_UP, Decimal


def currency_code(value, fallback="TRY") -> str:
    code = str(value or fallback).strip().upper() or fallback
    return "TRY" if code == "TL" else code


def money(value) -> Decimal:
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
